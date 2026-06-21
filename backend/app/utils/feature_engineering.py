"""
Feature engineering pipeline (roadmap section 5).

Design choices worth calling out explicitly:

1. NO LABEL LEAKAGE: `requires_road_closure` and `duration_mins` are real,
   recorded outcomes for historical events — but for any event we're
   actually forecasting (a what-if injection, or a real event the moment
   it's reported), neither of those is known yet. So neither field is used
   as an INPUT feature to any of the three models. They are only used to
   *construct the training labels* (e.g. the composite severity score).
   All three models — severity, closure, duration — consume exactly the
   same "pre-event" feature vector, which is also what keeps the system
   honest in the what-if demo: it genuinely cannot see the answer.

2. Categorical columns are kept as pandas `category` dtype and handed to
   LightGBM natively (no one-hot explosion) — but the *set* of categories
   is frozen at fit time and reused at transform time, so an unseen
   category at inference degrades gracefully to "missing" rather than
   crashing or silently creating a new column.

3. Recurrence features (`recurrence_7d` / `recurrence_30d`) are the one
   feature that requires a reference to historical data at inference time
   (the trailing window for a *new* incident has to look backward into
   real history). The fitted FeatureEngineer keeps a small, trimmed
   (h3_cell, start_dt) history table in memory for exactly this lookup —
   it is not used for anything else and is intentionally minimal.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from app.utils import time_utils, data_cleaning, geo_utils, nlp_tags

NUMERIC_FEATURES = [
    "hour_ist", "day_of_week", "is_weekend", "is_curfew_window", "month",
    "recurrence_7d", "recurrence_30d",
    "cause_closure_base_rate", "cause_median_duration_mins",
    "junction_freq",
] + nlp_tags.NLP_FLAG_COLUMNS

CATEGORICAL_FEATURES = [
    "event_cause", "event_type", "veh_type", "corridor", "police_station", "zone",
]

ALL_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES

_DEFAULT_CAT = "unknown"


@dataclass
class FeatureEngineer:
    fitted_: bool = False
    cause_closure_rate_: dict = field(default_factory=dict)
    cause_median_duration_: dict = field(default_factory=dict)
    junction_freq_: dict = field(default_factory=dict)
    category_levels_: dict = field(default_factory=dict)
    overall_closure_rate_: float = 0.083
    overall_median_duration_: float = 51.0
    history_: Optional[pd.DataFrame] = None  # trimmed (h3_cell, start_dt) for recurrence lookups

    # ── Fit ──────────────────────────────────────────────────────────────────

    def fit(self, raw_df: pd.DataFrame, duration_df: Optional[pd.DataFrame] = None) -> "FeatureEngineer":
        """
        raw_df: cleaned historical event dataframe (see app.utils.data_loading.clean_raw_events),
                must already have: event_cause, requires_road_closure, junction_norm,
                start_dt (parsed UTC timestamp), h3_cell.
        duration_df: optional dataframe with columns [event_cause, duration_mins] for
                events with a usable, non-censored duration (used only to compute the
                cause_median_duration_ feature, not as a model input).
        """
        df = raw_df.copy()

        # cause -> base closure rate (Laplace-smoothed so rare causes don't get 0%/100%)
        overall_rate = float(df["requires_road_closure"].mean()) if len(df) else 0.083
        self.overall_closure_rate_ = overall_rate
        grp = df.groupby("event_cause")["requires_road_closure"].agg(["sum", "count"])
        smoothed = (grp["sum"] + 2 * overall_rate) / (grp["count"] + 2)
        self.cause_closure_rate_ = smoothed.to_dict()

        # cause -> median duration (from the non-censored subset only)
        if duration_df is not None and len(duration_df) > 0:
            med = duration_df.groupby("event_cause")["duration_mins"].median()
            self.overall_median_duration_ = float(duration_df["duration_mins"].median())
            self.cause_median_duration_ = med.to_dict()
        else:
            self.overall_median_duration_ = 51.0
            self.cause_median_duration_ = {}

        # junction frequency encoding
        if "junction_norm" in df.columns:
            vc = df["junction_norm"].value_counts(normalize=True)
            self.junction_freq_ = vc.to_dict()

        # frozen categorical vocabularies
        for col in CATEGORICAL_FEATURES:
            if col in df.columns:
                seen = set(df[col].dropna().astype(str).unique().tolist())
                seen.discard(_DEFAULT_CAT)  # avoid a duplicate category if the
                                             # cleaned column already contains
                                             # the literal "unknown" sentinel
                                             # (e.g. veh_type via
                                             # data_cleaning.normalize_veh_type)
                self.category_levels_[col] = sorted(seen) + [_DEFAULT_CAT]
            else:
                self.category_levels_[col] = [_DEFAULT_CAT]

        # trimmed history for recurrence lookups
        if "h3_cell" in df.columns and "start_dt" in df.columns:
            hist = df[["h3_cell", "start_dt"]].dropna().sort_values("start_dt").reset_index(drop=True)
            self.history_ = hist

        self.fitted_ = True
        return self

    # ── Transform ────────────────────────────────────────────────────────────

    def transform(self, raw_df: pd.DataFrame) -> pd.DataFrame:
        """Build the model-ready feature matrix from a cleaned event dataframe."""
        assert self.fitted_, "FeatureEngineer must be fit() before transform()"
        df = raw_df.copy()

        # ── Temporal ──
        df["hour_ist"] = df["start_dt"].apply(time_utils.hour_ist).astype("float")
        df["day_of_week"] = df["start_dt"].apply(time_utils.day_of_week_ist).astype("float")
        df["is_weekend"] = df["start_dt"].apply(time_utils.is_weekend_ist).astype(int)
        df["is_curfew_window"] = df["hour_ist"].apply(
            lambda h: time_utils.is_curfew_window(int(h)) if pd.notna(h) else False
        ).astype(int)
        df["month"] = df["start_dt"].apply(time_utils.month_ist).astype("float")

        # ── Recurrence (trailing 7d / 30d count of events in the same H3 cell) ──
        df["recurrence_7d"], df["recurrence_30d"] = self._recurrence_counts(df)

        # ── Cause base-rate features ──
        df["cause_closure_base_rate"] = df["event_cause"].map(self.cause_closure_rate_).fillna(
            self.overall_closure_rate_
        )
        df["cause_median_duration_mins"] = df["event_cause"].map(self.cause_median_duration_).fillna(
            self.overall_median_duration_
        )

        # ── Junction frequency ──
        if "junction_norm" in df.columns:
            df["junction_freq"] = df["junction_norm"].map(self.junction_freq_).fillna(0.0)
        else:
            df["junction_freq"] = 0.0

        # ── NLP tags ──
        if "description" in df.columns:
            tags = df["description"].apply(nlp_tags.tag_description).apply(pd.Series)
            for col in nlp_tags.NLP_FLAG_COLUMNS:
                df[col] = tags[col].astype(int) if col in tags.columns else 0
        else:
            for col in nlp_tags.NLP_FLAG_COLUMNS:
                df[col] = 0

        # ── Categoricals (frozen vocabulary) ──
        for col in CATEGORICAL_FEATURES:
            levels = self.category_levels_.get(col, [_DEFAULT_CAT])
            if col in df.columns:
                vals = df[col].astype(str).where(df[col].notna(), _DEFAULT_CAT)
                vals = vals.where(vals.isin(levels), _DEFAULT_CAT)
            else:
                vals = pd.Series([_DEFAULT_CAT] * len(df), index=df.index)
            df[col] = pd.Categorical(vals, categories=levels)

        for col in NUMERIC_FEATURES:
            if col not in df.columns:
                df[col] = 0.0
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

        return df[ALL_FEATURES]

    def transform_one(self, event: dict) -> pd.DataFrame:
        """Convenience wrapper: build the feature row for a single event dict."""
        row = dict(event)
        if "start_dt" not in row or row.get("start_dt") is None:
            row["start_dt"] = time_utils.parse_utc(row.get("start_datetime")) or pd.Timestamp.now(tz="UTC")
        if "h3_cell" not in row:
            row["h3_cell"] = geo_utils.to_h3(row.get("latitude"), row.get("longitude"))
        if "junction_norm" not in row:
            row["junction_norm"] = data_cleaning.normalize_junction(row.get("junction"))
        if "event_cause" in row:
            row["event_cause"] = data_cleaning.normalize_event_cause(row["event_cause"])
        if "requires_road_closure" not in row:
            row["requires_road_closure"] = False
        df = pd.DataFrame([row])
        return self.transform(df)

    # ── internals ────────────────────────────────────────────────────────────

    def _recurrence_counts(self, df: pd.DataFrame):
        """
        For each row, count how many historical events fired in the same H3
        cell in the trailing 7 / 30 days before this row's start_dt. Uses the
        trimmed `history_` table captured at fit time via binary search
        (np.searchsorted) per H3 group — O(n log n), not O(n^2).
        """
        n = len(df)
        c7 = np.zeros(n, dtype=int)
        c30 = np.zeros(n, dtype=int)

        if self.history_ is None or len(self.history_) == 0:
            return c7, c30

        hist = self.history_
        hist_by_cell = {cell: grp["start_dt"].values for cell, grp in hist.groupby("h3_cell")}

        starts = df["start_dt"].values
        cells = df["h3_cell"].values if "h3_cell" in df.columns else [None] * n

        for i in range(n):
            cell = cells[i]
            ts = starts[i]
            if cell is None or pd.isna(ts):
                continue
            times = hist_by_cell.get(cell)
            if times is None or len(times) == 0:
                continue
            ts64 = np.datetime64(ts)
            lo7 = ts64 - np.timedelta64(7, "D")
            lo30 = ts64 - np.timedelta64(30, "D")
            # events strictly before this one's start, within the window
            hi_idx = np.searchsorted(times, ts64, side="left")
            lo7_idx = np.searchsorted(times, lo7, side="left")
            lo30_idx = np.searchsorted(times, lo30, side="left")
            c7[i] = max(0, hi_idx - lo7_idx)
            c30[i] = max(0, hi_idx - lo30_idx)

        return c7, c30
