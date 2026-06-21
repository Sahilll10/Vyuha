"""
/insights — the dataset EDA endpoints (roadmap section 3 / 9 Screen 4):
hourly curfew pattern, per-cause stats, per-corridor stats, and the
derived-severity-vs-raw-priority discrepancy chart. All served from the
InsightsCache, which is loaded once at startup from the processed
historical parquet file (not the live events DB, so what-if/simulated
events never quietly skew the dataset-level charts a judge will see).
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.models import schemas
from app.utils.insights_cache import insights_cache

router = APIRouter(prefix="/insights", tags=["insights"])


def _require_cache_ready():
    if not insights_cache.loaded:
        raise HTTPException(
            status_code=503,
            detail=insights_cache.load_error or "Insights cache is not loaded yet.",
        )


@router.get("/summary", response_model=schemas.SummaryResponse)
def get_summary():
    _require_cache_ready()
    return insights_cache.summary()


@router.get("/hourly-pattern", response_model=list[schemas.HourlyPatternPoint])
def get_hourly_pattern():
    """The headline insight: events spike 2-4 AM IST, tracking Bengaluru's
    heavy-vehicle entry curfew window (roadmap section 3.5)."""
    _require_cache_ready()
    return insights_cache.hourly_pattern()


@router.get("/cause-stats", response_model=list[schemas.CauseStatPoint])
def get_cause_stats():
    _require_cache_ready()
    return insights_cache.cause_stats()


@router.get("/corridor-stats", response_model=list[schemas.CorridorStatPoint])
def get_corridor_stats(top_n: int = 15):
    _require_cache_ready()
    return insights_cache.corridor_stats(top_n=top_n)


@router.get("/severity-vs-priority", response_model=list[schemas.SeverityVsPriorityPoint])
def get_severity_vs_priority():
    """Surfaces cases (e.g. tree_fall) where raw `priority` and our derived
    `severity` disagree — concrete evidence the ML layer adds information
    the existing manual field doesn't have (roadmap section 3.4 / 14)."""
    _require_cache_ready()
    return insights_cache.severity_vs_priority()


@router.get("/model-metrics")
def get_model_metrics():
    """
    Held-out accuracy/ROC-AUC/concordance-index and top LightGBM feature
    importances for each of the three models, written by
    scripts/train_models.py to settings.METRICS_PATH. Raw dict response
    (not a fixed Pydantic schema) since the shape is genuinely
    model-specific — this is what backs the dashboard's explainability
    story (roadmap section 11, "Explainability" row) without needing live
    per-request SHAP computation.
    """
    try:
        with open(settings.METRICS_PATH) as f:
            return json.load(f)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="No metrics file yet — run scripts/train_models.py first.",
        )
