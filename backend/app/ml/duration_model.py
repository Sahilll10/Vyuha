"""
Duration / resolution-time model — survival analysis, not naive regression.

Only ~35% of events have a clean closure timestamp; the other ~65% are
either still active or were closed without one ever being logged. Training
a regressor on only the 35% that happen to have a clean timestamp would
bias the model toward the easy/fast cases that get logged out cleanly.
Instead we treat every event as a survival-time observation: `observed=1`
for a true completed duration, `observed=0` for a right-censored one (the
event was alive at least until `modified_datetime`, true end unknown).

A Weibull Accelerated Failure Time model (`lifelines.WeibullAFTFitter`)
handles this correctly and gives a full predictive distribution, so we can
report a median *and* a [10th, 90th] percentile interval — "expect this to
take 35-70 minutes" is both more honest and more actionable on the
dashboard than a single point estimate (roadmap section 6.2).
"""
from __future__ import annotations

import joblib
import numpy as np
import pandas as pd
from lifelines import WeibullAFTFitter

from app.config import settings

_NUMERIC_COVARIATES = [
    "hour_ist", "is_curfew_window", "is_weekend", "month",
    "recurrence_7d", "recurrence_30d", "cause_closure_base_rate",
    "junction_freq", "has_description", "mentions_towing",
    "mentions_resolution_in_progress", "mentions_severe",
]


class DurationModel:
    def __init__(self, penalizer: float = 0.1):
        self.aft = WeibullAFTFitter(penalizer=penalizer)
        self.cause_categories_: list[str] = []
        self.feature_cols_: list[str] = []

    def _design_matrix(self, X: pd.DataFrame, fit: bool) -> pd.DataFrame:
        df = X.copy()

        cause_dummies = pd.get_dummies(df["event_cause"].astype(str), prefix="cause")
        if fit:
            self.cause_categories_ = cause_dummies.columns.tolist()
        else:
            for c in self.cause_categories_:
                if c not in cause_dummies.columns:
                    cause_dummies[c] = 0
            cause_dummies = cause_dummies[self.cause_categories_]

        is_planned = (df["event_type"].astype(str) == "planned").astype(int).rename("is_planned")

        numeric_cols = [c for c in _NUMERIC_COVARIATES if c in df.columns]
        numeric_df = df[numeric_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0).reset_index(drop=True)

        design = pd.concat(
            [numeric_df, is_planned.reset_index(drop=True), cause_dummies.reset_index(drop=True)],
            axis=1,
        )
        # lifelines needs at least some variance per column; drop all-zero columns at fit time only
        if fit:
            nonconstant = [c for c in design.columns if design[c].nunique() > 1]
            design = design[nonconstant]
            self.feature_cols_ = design.columns.tolist()
        else:
            for c in self.feature_cols_:
                if c not in design.columns:
                    design[c] = 0
            design = design[self.feature_cols_]
        return design

    def fit(self, X: pd.DataFrame, duration_mins: pd.Series, observed: pd.Series) -> "DurationModel":
        design = self._design_matrix(X, fit=True)
        design = design.reset_index(drop=True)
        design["duration_mins"] = np.maximum(duration_mins.values, 1.0)  # AFT requires strictly positive durations
        design["observed"] = observed.values.astype(int)
        self.aft.fit(design, duration_col="duration_mins", event_col="observed")
        return self

    def predict(self, X: pd.DataFrame):
        """Returns (median_mins, lower_mins[~p10], upper_mins[~p90]) as numpy arrays."""
        design = self._design_matrix(X, fit=False)
        cap = settings.DURATION_CAP_MINS

        median = self.aft.predict_percentile(design, p=0.5)
        lower = self.aft.predict_percentile(design, p=0.9)   # S(t)=0.9 -> small t -> ~10th pct of duration
        upper = self.aft.predict_percentile(design, p=0.1)   # S(t)=0.1 -> large t -> ~90th pct of duration

        def _clean(series):
            arr = series.replace([np.inf, -np.inf], cap).fillna(cap).values
            return np.clip(arr, 1.0, cap)

        return _clean(median), _clean(lower), _clean(upper)

    def save(self, path: str = None):
        joblib.dump(self, path or settings.DURATION_MODEL_PATH)

    @staticmethod
    def load(path: str = None) -> "DurationModel":
        return joblib.load(path or settings.DURATION_MODEL_PATH)
