"""
Severity classifier — LightGBM multiclass model predicting the composite
Low/Medium/High severity label built in app.utils.data_loading.build_severity_label.

LightGBM (not a deep model) is the deliberate choice here: fast to train
and iterate on ~8K rows, handles the native pandas `category` dtype
columns from the feature pipeline without one-hot blowup, gives free
feature importances for the dashboard's explainability screen, and is far
less likely to silently overfit a dataset this size than a neural net —
see roadmap section 6.1.
"""
from __future__ import annotations

import joblib
import pandas as pd
from lightgbm import LGBMClassifier

from app.config import settings
from app.utils.feature_engineering import CATEGORICAL_FEATURES

SEVERITY_LABELS = ["Low", "Medium", "High"]
_LABEL_TO_IDX = {label: i for i, label in enumerate(SEVERITY_LABELS)}


class SeverityModel:
    def __init__(self):
        self.model = LGBMClassifier(
            n_estimators=300,
            num_leaves=31,
            max_depth=-1,
            learning_rate=0.05,
            objective="multiclass",
            num_class=3,
            class_weight="balanced",
            min_child_samples=15,
            random_state=42,
            verbosity=-1,
        )

    def fit(self, X: pd.DataFrame, y: pd.Series, sample_weight=None) -> "SeverityModel":
        y_idx = y.map(_LABEL_TO_IDX)
        cat_cols = [c for c in CATEGORICAL_FEATURES if c in X.columns]
        self.model.fit(X, y_idx, sample_weight=sample_weight, categorical_feature=cat_cols)
        return self

    def predict(self, X: pd.DataFrame):
        """Returns (labels: List[str], confidence: np.ndarray, proba: np.ndarray)."""
        proba = self.model.predict_proba(X)
        idx = proba.argmax(axis=1)
        labels = [SEVERITY_LABELS[i] for i in idx]
        confidence = proba.max(axis=1)
        return labels, confidence, proba

    def feature_importance(self) -> dict:
        return dict(zip(self.model.feature_name_, self.model.feature_importances_.tolist()))

    def save(self, path: str = None):
        joblib.dump(self.model, path or settings.SEVERITY_MODEL_PATH)

    def load(self, path: str = None) -> "SeverityModel":
        self.model = joblib.load(path or settings.SEVERITY_MODEL_PATH)
        return self
