"""
Database layer — SQLAlchemy ORM models and session factory.
Uses SQLite for development (trivially swappable to Postgres + PostGIS for production).
"""
from sqlalchemy import (
    create_engine, Column, String, Float, Boolean,
    DateTime, Integer, Text
)
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime, timezone

from app.config import settings

# ─── Engine ───────────────────────────────────────────────────────────────────

_connect_args = {}
if "sqlite" in settings.DATABASE_URL:
    _connect_args = {"check_same_thread": False}

engine = create_engine(settings.DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def _utcnow():
    return datetime.now(timezone.utc)


# ─── ORM Models ───────────────────────────────────────────────────────────────

class EventDB(Base):
    """One traffic event from ASTraM (historical or simulated what-if)."""
    __tablename__ = "events"

    id = Column(String, primary_key=True, index=True)
    event_type = Column(String)                          # planned / unplanned
    event_cause = Column(String)                         # vehicle_breakdown, etc.
    latitude = Column(Float)
    longitude = Column(Float)
    endlatitude = Column(Float, nullable=True)
    endlongitude = Column(Float, nullable=True)
    address = Column(Text, nullable=True)
    end_address = Column(Text, nullable=True)
    corridor = Column(String, nullable=True)
    police_station = Column(String, nullable=True)
    junction = Column(String, nullable=True)
    zone = Column(String, nullable=True)
    priority = Column(String, nullable=True)             # High / Low (raw field)
    requires_road_closure = Column(Boolean, default=False)
    status = Column(String, default="active")             # active / closed / resolved
    veh_type = Column(String, nullable=True)
    veh_no = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    route_path = Column(Text, nullable=True)
    start_datetime = Column(DateTime, nullable=True)
    end_datetime = Column(DateTime, nullable=True)
    modified_datetime = Column(DateTime, nullable=True)
    closed_datetime = Column(DateTime, nullable=True)
    resolved_datetime = Column(DateTime, nullable=True)
    resolved_at_latitude = Column(Float, nullable=True)
    resolved_at_longitude = Column(Float, nullable=True)
    resolved_at_address = Column(Text, nullable=True)

    # Meta
    is_simulated = Column(Boolean, default=False)        # True = what-if event
    ingested_at = Column(DateTime, default=_utcnow)


class PredictionDB(Base):
    """Model prediction output for one event."""
    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String, index=True)
    severity = Column(String)                 # Low / Medium / High
    severity_confidence = Column(Float)       # max class probability
    closure_probability = Column(Float)       # P(road closure needed)
    duration_median_mins = Column(Float)
    duration_lower_mins = Column(Float)       # ~10th percentile
    duration_upper_mins = Column(Float)       # ~90th percentile
    predicted_at = Column(DateTime, default=_utcnow)
    model_version = Column(String, default="1.0")


class FeedbackDB(Base):
    """
    Post-event ground truth logged by officers.
    Feeds the retraining loop (Module 6 in the roadmap).
    """
    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String, index=True)
    actual_duration_mins = Column(Float, nullable=True)
    actual_closure_needed = Column(Boolean, nullable=True)
    actual_severity = Column(String, nullable=True)      # Low / Medium / High
    officers_deployed = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    submitted_at = Column(DateTime, default=_utcnow)


# ─── Utilities ────────────────────────────────────────────────────────────────

def create_tables():
    """Create all tables. Safe to call multiple times (no-op if exists)."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency — yields a DB session and closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
