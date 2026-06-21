"""
Central configuration — all paths, constants, and env settings.
Edit .env to override; never hard-code secrets in source.
"""
from pydantic_settings import BaseSettings
from pathlib import Path
from typing import List


class Settings(BaseSettings):
    # ── Server ────────────────────────────────────────────────────────────────
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = True

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "sqlite:///./vyuha.db"

    # ── Paths ─────────────────────────────────────────────────────────────────
    MODELS_DIR: str = "./saved_models"
    DATA_DIR: str = "./data"
    RAW_DATA_FILE: str = "./data/raw/astram_events.csv"
    PROCESSED_DATA_FILE: str = "./data/processed/events_processed.parquet"
    DURATION_TRAIN_FILE: str = "./data/processed/duration_training_subset.parquet"

    # ── CORS ──────────────────────────────────────────────────────────────────
    CORS_ORIGINS_STR: str = (
        "http://localhost:3000,http://localhost:5173,http://localhost:5174,http://localhost:4173"
    )

    # ── Bengaluru bounding box ────────────────────────────────────────────────
    LAT_MIN: float = 12.80
    LAT_MAX: float = 13.27
    LNG_MIN: float = 77.31
    LNG_MAX: float = 77.77

    # ── Timezone ──────────────────────────────────────────────────────────────
    IST_OFFSET_HOURS: int = 5
    IST_OFFSET_MINUTES: int = 30

    # ── Heavy-vehicle curfew window (IST hours) ───────────────────────────────
    # Bengaluru bans goods vehicles >3T during the daytime/evening peak.
    # They ARE on roads at night -> breakdown spike at 02:00-04:00 IST.
    CURFEW_ALLOWED_START: int = 22   # 10 PM — vehicles allowed from here
    CURFEW_ALLOWED_END: int = 7      # 7 AM  — vehicles must exit by here

    # ── Model artifact paths ──────────────────────────────────────────────────
    SEVERITY_MODEL_PATH: str = "./saved_models/severity_model.joblib"
    CLOSURE_MODEL_PATH: str = "./saved_models/closure_model.joblib"
    DURATION_MODEL_PATH: str = "./saved_models/duration_model.joblib"
    FEATURE_ENGINEER_PATH: str = "./saved_models/feature_engineer.joblib"
    METRICS_PATH: str = "./saved_models/metrics.json"

    # ── Duration cap (minutes) — anything above is treated as a logging outlier
    DURATION_CAP_MINS: float = 2880.0   # 48 hours

    # ── H3 spatial index resolution (8 ≈ ~460m hex edge length) ───────────────
    H3_RESOLUTION: int = 8

    # ── Routing / OSM cache ────────────────────────────────────────────────────
    OSM_GRAPH_CACHE: str = "./data/processed/bengaluru_drive.graphml"
    OSM_PLACE_NAME: str = "Bengaluru, Karnataka, India"

    # ── Station capacity default (used by the manpower allocator demo) ───────
    DEFAULT_STATION_CAPACITY: int = 10

    @property
    def CORS_ORIGINS(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS_STR.split(",") if o.strip()]

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()

# Ensure required directories exist at import time
for _dir in [
    settings.MODELS_DIR,
    settings.DATA_DIR,
    "./data/raw",
    "./data/processed",
]:
    Path(_dir).mkdir(parents=True, exist_ok=True)
