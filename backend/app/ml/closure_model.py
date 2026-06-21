"""
Road-closure probability — LightGBM binary classifier predicting
`requires_road_closure`. Only 8.3% of historical events require a full
closure, so class_weight="balanced" is used to keep the model from just
always predicting False. This single probability is the trigger condition
the recommendation engine uses to decide whether barricading/diversion
modules activate at all (roadmap section 6.3 / 7.2).
"""
from __future__ import annotations

import joblib
import pandas as pd
from lightgbm import LGBMClassifier

from app.config import settings
from app.utils.feature_engineering import CATEGORICAL_FEATURES


class ClosureModel:
    def __init__(self):
        self.model = LGBMClassifier(
            n_estimators=300,
            num_leaves=31,
            max_depth=-1,
            learning_rate=0.05,
            objective="binary",
            class_weight="balanced",
            min_child_samples=15,
            random_state=42,
            verbosity=-1,
        )

    def fit(self, X: pd.DataFrame, y: pd.Series, sample_weight=None) -> "ClosureModel":
        cat_cols = [c for c in CATEGORICAL_FEATURES if c in X.columns]
        self.model.fit(X, y.astype(int), sample_weight=sample_weight, categorical_feature=cat_cols)
        return self

    def predict_proba(self, X: pd.DataFrame):
        return self.model.predict_proba(X)[:, 1]

    def feature_importance(self) -> dict:
        return dict(zip(self.model.feature_name_, self.model.feature_importances_.tolist()))

    def save(self, path: str = None):
        joblib.dump(self.model, path or settings.CLOSURE_MODEL_PATH)

    def load(self, path: str = None) -> "ClosureModel":
        self.model = joblib.load(path or settings.CLOSURE_MODEL_PATH)
        return self
