"""
Shared data loading, cleaning, duration/censoring, and label-construction
logic. Used by scripts/preprocess.py (offline) and by the live API when a
new event needs the same cleaning applied before being scored.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from app.config import settings
from app.utils import data_cleaning, geo_utils, time_utils

RAW_DATETIME_COLS = [
    "start_datetime", "end_datetime", "modified_datetime",
    "closed_datetime", "resolved_datetime", "created_date",
]

# cause -> weight used by the composite severity rule (roadmap 6.1).
# Causes not listed default to 0. These weights were chosen so that
# vip_movement / public_event / protest (the dramatic, low-frequency,
# high-disruption cases the problem statement leads with) reliably push
# into High severity, while the high-frequency, low-disruption
# vehicle_breakdown majority does not, by default.
_CAUSE_SEVERITY_WEIGHT = {
    "vip_movement": 2, "public_event": 2, "protest": 2,
    "tree_fall": 1, "procession": 1, "construction": 1,
    "water_logging": 1, "road_conditions": 1, "accident": 1,
    "congestion": 1, "debris": 1,
    "pot_holes": 0, "vehicle_breakdown": 0, "others": 0,
}


def load_raw_csv(path: Optional[str] = None) -> pd.DataFrame:
    path = path or settings.RAW_DATA_FILE
    return pd.read_csv(path)


def clean_raw_events(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply all the cleaning steps from roadmap section 3/5 to a raw events
    dataframe (or a single-row dataframe built from a what-if request).
    Adds: start_dt (parsed UTC), h3_cell, junction_norm, event_cause
    (normalized), priority (normalized), veh_type (normalized), status
    (normalized), endlatitude/endlongitude with the 0.0 sentinel cleared.
    """
    out = df.copy()

    # NOTE: parsed with vectorized pd.to_datetime (not `.apply(parse_utc)`).
    # Applying a function that returns a mix of pd.Timestamp/None row-by-row
    # leaves the column as `object` dtype, not `datetime64[ns, UTC]` — which
    # later breaks `(end_ts - start_ts)` arithmetic in
    # compute_duration_and_censoring with a cryptic dtype error. Vectorized
    # `pd.to_datetime(..., utc=True, errors="coerce")` parses the whole
    # column directly into a proper tz-aware datetime64 Series.
    for col in RAW_DATETIME_COLS:
        if col in out.columns:
            out[col + "_dt"] = pd.to_datetime(out[col], utc=True, errors="coerce")
        else:
            out[col + "_dt"] = pd.Series(pd.NaT, index=out.index)
    out["start_dt"] = out.get(
        "start_datetime_dt", pd.Series(pd.NaT, index=out.index)
    )

    if "event_cause" in out.columns:
        out["event_cause"] = out["event_cause"].apply(data_cleaning.normalize_event_cause)
    if "priority" in out.columns:
        out["priority"] = out["priority"].apply(data_cleaning.normalize_priority)
    if "veh_type" in out.columns:
        out["veh_type"] = out["veh_type"].apply(data_cleaning.normalize_veh_type)
    if "status" in out.columns:
        out["status"] = out["status"].apply(data_cleaning.normalize_status)
    if "junction" in out.columns:
        out["junction_norm"] = out["junction"].apply(data_cleaning.normalize_junction)
    else:
        out["junction_norm"] = None

    for col in ["endlatitude", "endlongitude"]:
        if col in out.columns:
            out[col] = out[col].apply(data_cleaning.clean_end_coordinate)
        else:
            out[col] = None

    if "requires_road_closure" in out.columns:
        out["requires_road_closure"] = out["requires_road_closure"].fillna(False).astype(bool)
    else:
        out["requires_road_closure"] = False

    out["h3_cell"] = out.apply(
        lambda r: geo_utils.to_h3(r.get("latitude"), r.get("longitude")), axis=1
    )

    for col in ["corridor", "police_station", "zone"]:
        if col not in out.columns:
            out[col] = None
        else:
            out[col] = out[col].where(out[col].notna(), None)
    if "corridor" in out.columns:
        out["corridor"] = out["corridor"].fillna("Non-corridor")

    if "event_type" not in out.columns:
        out["event_type"] = "unplanned"
    else:
        out["event_type"] = out["event_type"].fillna("unplanned").str.lower()

    return out


def compute_duration_and_censoring(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds `duration_mins` and `observed` (1 = true completed duration,
    0 = right-censored — event was still alive at last known timestamp).

    closed_datetime is preferred, falling back to resolved_datetime, then
    end_datetime. If none are usable, the event is censored at
    modified_datetime (the last time the record was touched at all).
    Durations beyond DURATION_CAP_MINS are treated as logging noise and
    re-censored at the cap rather than trusted at face value — this avoids
    a handful of multi-day "durations" (almost certainly stale/unclosed
    records) from distorting the survival fit.
    """
    out = df.copy()
    end_ts = out.get("closed_datetime_dt")
    if end_ts is None:
        end_ts = pd.Series([pd.NaT] * len(out), index=out.index)
    end_ts = end_ts.fillna(out.get("resolved_datetime_dt"))
    end_ts = end_ts.fillna(out.get("end_datetime_dt"))

    start_ts = out["start_dt"]
    raw_duration = (end_ts - start_ts).dt.total_seconds() / 60.0
    has_valid_end = end_ts.notna() & start_ts.notna() & (raw_duration > 0)

    modified_ts = out.get("modified_datetime_dt")
    censored_duration = None
    if modified_ts is not None:
        censored_duration = (modified_ts - start_ts).dt.total_seconds() / 60.0

    duration_mins = np.where(has_valid_end, raw_duration, np.nan)
    observed = np.where(has_valid_end, 1, 0).astype(int)

    if censored_duration is not None:
        fallback = censored_duration.values
        needs_fallback = ~has_valid_end.values
        valid_fallback = needs_fallback & (fallback > 0) & ~np.isnan(fallback)
        duration_mins = np.where(valid_fallback, fallback, duration_mins)

    # anything still NaN (no usable timestamp at all) gets a conservative
    # minimum censoring time of 5 minutes so it can still contribute to the
    # survival fit as "alive at least 5 minutes" rather than being dropped.
    duration_mins = np.where(np.isnan(duration_mins), 5.0, duration_mins)

    cap = settings.DURATION_CAP_MINS
    over_cap = duration_mins > cap
    duration_mins = np.where(over_cap, cap, duration_mins)
    observed = np.where(over_cap, 0, observed)

    out["duration_mins"] = duration_mins
    out["observed"] = observed
    return out


def build_severity_label(df: pd.DataFrame) -> pd.Series:
    """
    Composite severity score (roadmap 6.1) — deliberately *not* a copy of
    the raw `priority` field. Combines:
      - requires_road_closure (ground truth, training-time only)
      - duration bucket (only when observed / non-censored)
      - a hand-set cause weight reflecting typical disruption magnitude
    This is the label the severity classifier is trained to predict, and
    is also what /insights/severity-vs-priority compares against the raw
    `priority` field to surface cases like tree_fall where they disagree.
    """
    score = pd.Series(0, index=df.index, dtype=int)
    if "requires_road_closure" in df.columns:
        score = score + df["requires_road_closure"].fillna(False).astype(int) * 2
    if "event_cause" in df.columns:
        score = score + df["event_cause"].map(_CAUSE_SEVERITY_WEIGHT).fillna(0).astype(int)
    if "duration_mins" in df.columns and "observed" in df.columns:
        dur = df["duration_mins"]
        observed = df["observed"].astype(bool)
        dur_term = pd.Series(0, index=df.index, dtype=int)
        dur_term = dur_term.where(~(observed & (dur > 60)), 1)
        dur_term = dur_term.where(~(observed & (dur > 180)), 2)
        score = score + dur_term

    severity = pd.Series("Low", index=df.index)
    severity = severity.where(score < 1, "Medium")
    severity = severity.where(score < 3, "High")
    return severity


def build_training_frame(raw_csv_path: Optional[str] = None) -> pd.DataFrame:
    """
    One-shot convenience: load -> clean -> compute duration/censoring ->
    attach the composite severity label. This is the single source of
    truth used by scripts/preprocess.py and scripts/train_models.py so
    training and any offline re-derivation never drift apart.
    """
    raw = load_raw_csv(raw_csv_path)
    cleaned = clean_raw_events(raw)
    with_duration = compute_duration_and_censoring(cleaned)
    with_duration["severity"] = build_severity_label(with_duration)
    return with_duration
