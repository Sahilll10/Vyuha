"""
VYUHA backend — FastAPI application entry point.

Startup sequence:
  1. Create DB tables (no-op if they already exist).
  2. Load the three trained predictive models + the fitted FeatureEngineer.
  3. Load the insights cache (precomputed EDA tables for the dashboard).
  4. Load the road graph (real OSM if reachable, otherwise the
     dataset-derived fallback graph) for diversion routing.

None of these failing should crash the app — a hackathon demo that 500s on
startup because the model files haven't been trained yet is worse than one
that boots cleanly and reports "models not loaded yet" on the relevant
endpoints. See `/health` for live status of every subsystem.
"""
from __future__ import annotations

import logging

import pandas as pd
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import create_tables, EventDB, SessionLocal
from app.ml.predictor import predictor
from app.recommender.routing import road_graph
from app.routers import events, predict, recommend, insights
from app.utils.insights_cache import insights_cache

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("vyuha.main")

app = FastAPI(
    title="VYUHA — व्यूह",
    description=(
        "Predictive & Prescriptive Event-Response System for Bengaluru Traffic. "
        "Gridlock Hackathon 2.0 — Flipkart x Bengaluru Traffic Police."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(events.router)
app.include_router(predict.router)
app.include_router(recommend.router)
app.include_router(insights.router)


def _build_junctions_df_for_fallback_graph() -> pd.DataFrame | None:
    """
    Builds the (node_id, lat, lon) table the fallback road graph routes
    over, by averaging coordinates within each H3 cell of the processed
    historical dataset. Every event has an h3_cell (derived straight from
    lat/lon), so this works even though the raw `junction` field itself is
    only populated for ~31% of rows.
    """
    try:
        df = pd.read_parquet(settings.PROCESSED_DATA_FILE)
    except FileNotFoundError:
        return None
    if "h3_cell" not in df.columns:
        return None
    grouped = (
        df.dropna(subset=["h3_cell", "latitude", "longitude"])
        .groupby("h3_cell")[["latitude", "longitude"]]
        .mean()
        .reset_index()
    )
    grouped = grouped.rename(columns={"h3_cell": "node_id", "latitude": "lat", "longitude": "lon"})
    return grouped


@app.on_event("startup")
def on_startup():
    logger.info("VYUHA backend starting up...")
    create_tables()

    predictor.load()
    insights_cache.load()

    junctions_df = _build_junctions_df_for_fallback_graph()
    road_graph.load(junctions_df=junctions_df)

    logger.info(
        "Startup complete. predictor.loaded=%s insights_cache.loaded=%s road_graph.mode=%s",
        predictor.loaded, insights_cache.loaded, road_graph.mode,
    )


@app.get("/health")
def health():
    db = SessionLocal()
    try:
        event_count = db.query(EventDB).count()
    except Exception:
        event_count = None
    finally:
        db.close()

    return {
        "status": "ok",
        "predictor": {
            "loaded": predictor.loaded,
            "error": predictor.load_error,
        },
        "insights_cache": {
            "loaded": insights_cache.loaded,
            "error": insights_cache.load_error,
        },
        "road_graph": {
            "mode": road_graph.mode,
            "nodes": road_graph.graph.number_of_nodes() if road_graph.graph is not None else 0,
            "edges": road_graph.graph.number_of_edges() if road_graph.graph is not None else 0,
        },
        "events_in_db": event_count,
    }


@app.get("/")
def root():
    return {
        "name": "VYUHA — व्यूह",
        "tagline": "Predictive & Prescriptive Event-Response System for Bengaluru Traffic",
        "docs": "/docs",
        "health": "/health",
    }
