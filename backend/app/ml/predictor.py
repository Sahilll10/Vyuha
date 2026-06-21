"""
Unified predictor — the single entry point the API (and the recommender
modules) use to go from a raw event dict to a full prediction.

Wraps the fitted FeatureEngineer + the three trained models (severity,
closure, duration) behind one `.predict_event()` call so routers never
have to know about feature columns, model internals, or load order.
Loaded once at FastAPI startup and reused across requests (loading three
model artifacts per request would be wasteful and slow down the what-if
demo's "instant" feel — see roadmap section 8.2).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import joblib
import pandas as pd

from app.config import settings
from app.ml.severity_model import SeverityModel
from app.ml.closure_model import ClosureModel
from app.ml.duration_model import DurationModel
from app.utils.feature_engineering import FeatureEngineer

logger = logging.getLogger("vyuha.predictor")


class Predictor:
    def __init__(self):
        self.feature_engineer: Optional[FeatureEngineer] = None
        self.severity_model: Optional[SeverityModel] = None
        self.closure_model: Optional[ClosureModel] = None
        self.duration_model: Optional[DurationModel] = None
        self.loaded: bool = False
        self.load_error: Optional[str] = None

    def load(self) -> "Predictor":
        try:
            self.feature_engineer = joblib.load(settings.FEATURE_ENGINEER_PATH)

            self.severity_model = SeverityModel()
            self.severity_model.load(settings.SEVERITY_MODEL_PATH)

            self.closure_model = ClosureModel()
            self.closure_model.load(settings.CLOSURE_MODEL_PATH)

            self.duration_model = DurationModel.load(settings.DURATION_MODEL_PATH)

            self.loaded = True
            self.load_error = None
            logger.info("Predictor: all model artifacts loaded successfully.")
        except FileNotFoundError as e:
            self.loaded = False
            self.load_error = (
                f"Model artifacts not found ({e}). Run `python scripts/preprocess.py` "
                "then `python scripts/train_models.py` before starting the API."
            )
            logger.warning(self.load_error)
        except Exception as e:  # pragma: no cover
            self.loaded = False
            self.load_error = f"Unexpected error loading models: {e}"
            logger.exception(self.load_error)
        return self

    def predict_event(self, event: dict, event_id: Optional[str] = None) -> dict:
        """
        event: a dict with at least latitude, longitude, event_cause,
        event_type, and optionally start_datetime/corridor/police_station/
        zone/veh_type/junction/description. Missing optional fields degrade
        gracefully via the FeatureEngineer's frozen 'unknown' bucket.
        """
        if not self.loaded:
            raise RuntimeError(self.load_error or "Predictor models are not loaded.")

        X = self.feature_engineer.transform_one(event)

        severity_labels, severity_conf, _ = self.severity_model.predict(X)
        closure_prob = self.closure_model.predict_proba(X)
        median, lower, upper = self.duration_model.predict(X)

        return {
            "event_id": event_id or event.get("id") or "unscored",
            "severity": severity_labels[0],
            "severity_confidence": float(severity_conf[0]),
            "closure_probability": float(closure_prob[0]),
            "duration_median_mins": float(median[0]),
            "duration_lower_mins": float(lower[0]),
            "duration_upper_mins": float(upper[0]),
            "predicted_at": datetime.now(timezone.utc),
            "model_version": "1.0",
        }

    def predict_batch(self, events_df: pd.DataFrame) -> pd.DataFrame:
        """Vectorized prediction for many events at once (used by /insights and bulk replay)."""
        if not self.loaded:
            raise RuntimeError(self.load_error or "Predictor models are not loaded.")

        X = self.feature_engineer.transform(events_df)
        labels, conf, _ = self.severity_model.predict(X)
        closure_prob = self.closure_model.predict_proba(X)
        median, lower, upper = self.duration_model.predict(X)

        out = events_df.copy().reset_index(drop=True)
        out["pred_severity"] = labels
        out["pred_severity_confidence"] = conf
        out["pred_closure_probability"] = closure_prob
        out["pred_duration_median_mins"] = median
        out["pred_duration_lower_mins"] = lower
        out["pred_duration_upper_mins"] = upper
        return out


# Module-level singleton, populated at FastAPI startup (see app/main.py)
predictor = Predictor()
