"""
/events — the core event lifecycle endpoints:
  - POST /events/simulate          the what-if injector (roadmap 8.2)
  - POST /events/load-historical   bulk-load the ASTraM CSV into the DB
  - GET  /events/active            for the command map (roadmap 9, Screen 1)
  - GET  /events/{event_id}        single event + latest prediction
  - GET  /events/{event_id}/response-card   full Event Response Card
  - GET  /events/replay/stream     chronological batch for historical replay (roadmap 8.1)
  - POST /events/feedback          post-event outcome logging (roadmap module 6)
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import EventDB, PredictionDB, FeedbackDB, get_db
from app.models import schemas
from app.ml.predictor import predictor
from app.recommender.response_card import build_response_card
from app.utils import data_cleaning, data_loading, time_utils

logger = logging.getLogger("vyuha.routers.events")
router = APIRouter(prefix="/events", tags=["events"])


# ─── Helpers ────────────────────────────────────────────────────────────────

def _event_db_to_dict(ev: EventDB) -> dict:
    return {
        "id": ev.id,
        "event_type": ev.event_type,
        "event_cause": ev.event_cause,
        "latitude": ev.latitude,
        "longitude": ev.longitude,
        "endlatitude": ev.endlatitude,
        "endlongitude": ev.endlongitude,
        "address": ev.address,
        "corridor": ev.corridor,
        "police_station": ev.police_station,
        "junction": ev.junction,
        "zone": ev.zone,
        "priority": ev.priority,
        "requires_road_closure": bool(ev.requires_road_closure),
        "status": ev.status,
        "veh_type": ev.veh_type,
        "description": ev.description,
        "start_datetime": ev.start_datetime,
    }


def _event_db_to_response(ev: EventDB, pred: Optional[PredictionDB] = None) -> dict:
    d = _event_db_to_dict(ev)
    d["start_datetime"] = ev.start_datetime.isoformat() if ev.start_datetime else None
    d["is_simulated"] = bool(ev.is_simulated)
    d["prediction"] = (
        {
            "event_id": pred.event_id,
            "severity": pred.severity,
            "severity_confidence": pred.severity_confidence,
            "closure_probability": pred.closure_probability,
            "duration_median_mins": pred.duration_median_mins,
            "duration_lower_mins": pred.duration_lower_mins,
            "duration_upper_mins": pred.duration_upper_mins,
            "predicted_at": pred.predicted_at,
        }
        if pred is not None else None
    )
    return d


def _latest_prediction(db: Session, event_id: str) -> Optional[PredictionDB]:
    return (
        db.query(PredictionDB)
        .filter(PredictionDB.event_id == event_id)
        .order_by(PredictionDB.predicted_at.desc())
        .first()
    )


def _persist_prediction(db: Session, prediction: dict) -> PredictionDB:
    row = PredictionDB(
        event_id=prediction["event_id"],
        severity=prediction["severity"],
        severity_confidence=prediction["severity_confidence"],
        closure_probability=prediction["closure_probability"],
        duration_median_mins=prediction["duration_median_mins"],
        duration_lower_mins=prediction["duration_lower_mins"],
        duration_upper_mins=prediction["duration_upper_mins"],
        model_version=prediction.get("model_version", "1.0"),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _require_predictor_ready():
    if not predictor.loaded:
        raise HTTPException(
            status_code=503,
            detail=predictor.load_error or "Models are not loaded yet. Train and restart the API.",
        )


# ─── Endpoints ──────────────────────────────────────────────────────────────

@router.post("/simulate", response_model=schemas.EventResponseCard)
def simulate_event(payload: schemas.EventCreateRequest, db: Session = Depends(get_db)):
    """
    The what-if injector (roadmap section 8.2) — the best moment in the
    demo. Creates a brand-new event from a judge/operator-submitted form,
    runs it through the full pipeline, and returns the complete Event
    Response Card within a single request.
    """
    _require_predictor_ready()

    event_id = f"SIM-{uuid.uuid4().hex[:10].upper()}"
    start_dt = payload.start_datetime or datetime.now(timezone.utc)

    ev = EventDB(
        id=event_id,
        event_type=payload.event_type,
        event_cause=payload.event_cause,
        latitude=payload.latitude,
        longitude=payload.longitude,
        endlatitude=payload.endlatitude,
        endlongitude=payload.endlongitude,
        address=payload.address,
        corridor=payload.corridor or "Non-corridor",
        police_station=payload.police_station,
        junction=payload.junction,
        zone=payload.zone,
        priority=None,
        requires_road_closure=False,   # unknown until predicted — this is a what-if event
        status="active",
        veh_type=payload.veh_type,
        description=payload.description,
        start_datetime=start_dt,
        is_simulated=True,
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)

    event_dict = _event_db_to_dict(ev)
    event_dict["junction_norm"] = data_cleaning.normalize_junction(payload.junction)

    prediction = predictor.predict_event(event_dict, event_id=event_id)
    _persist_prediction(db, prediction)

    concurrent = (
        db.query(func.count(EventDB.id))
        .filter(EventDB.police_station == ev.police_station, EventDB.status == "active")
        .scalar()
        if ev.police_station else None
    )

    extras = build_response_card(
        event={**event_dict, "requires_road_closure": None},  # let the predicted probability decide
        prediction=prediction,
        concurrent_active_in_station=concurrent,
    )

    return {
        "event": _event_db_to_response(ev),
        "prediction": prediction,
        "manpower": extras["manpower"],
        "barricade": extras["barricade"],
        "diversion": extras["diversion"],
    }


@router.post("/load-historical")
def load_historical(limit: Optional[int] = Query(default=None, ge=1), db: Session = Depends(get_db)):
    """
    Bulk-loads the cleaned ASTraM CSV into the events table.
    Safe to call multiple times — existing IDs are skipped.
    """

    try:
        cleaned = data_loading.build_training_frame()
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Raw CSV not found."
        )

    if limit:
        cleaned = cleaned.head(limit)

    # CRITICAL FIX
    cleaned = cleaned.where(pd.notnull(cleaned), None)

    existing_ids = {row[0] for row in db.query(EventDB.id).all()}

    loaded = 0
    skipped = 0

    for _, r in cleaned.iterrows():

        rid = str(r.get("id"))

        if rid in existing_ids:
            skipped += 1
            continue

        def safe(v):
            return None if pd.isna(v) else v

        ev = EventDB(
            id=rid,
            event_type=safe(r.get("event_type")),
            event_cause=safe(r.get("event_cause")),
            latitude=safe(r.get("latitude")),
            longitude=safe(r.get("longitude")),
            endlatitude=safe(r.get("endlatitude")),
            endlongitude=safe(r.get("endlongitude")),
            address=safe(r.get("address")),
            end_address=safe(r.get("end_address")),
            corridor=safe(r.get("corridor")),
            police_station=safe(r.get("police_station")),
            junction=safe(r.get("junction")),
            zone=safe(r.get("zone")),

            # FIXED
            priority=str(r["priority"]) if pd.notna(r.get("priority")) else None,

            # FIXED
            requires_road_closure=bool(r["requires_road_closure"])
            if pd.notna(r.get("requires_road_closure"))
            else False,

            status=safe(r.get("status")) or "closed",
            veh_type=safe(r.get("veh_type")),
            veh_no=safe(r.get("veh_no")),
            description=safe(r.get("description")),
            route_path=safe(r.get("route_path")),

            start_datetime=safe(r.get("start_dt")),
            closed_datetime=safe(r.get("closed_datetime_dt")),
            resolved_datetime=safe(r.get("resolved_datetime_dt")),

            resolved_at_latitude=safe(r.get("resolved_at_latitude")),
            resolved_at_longitude=safe(r.get("resolved_at_longitude")),
            resolved_at_address=safe(r.get("resolved_at_address")),

            is_simulated=False,
        )

        db.add(ev)
        loaded += 1

        if loaded % 500 == 0:
            db.commit()

    db.commit()

    return {
        "loaded": loaded,
        "skipped": skipped,
        "total_in_db": loaded + len(existing_ids),
    }
@router.get("/active", response_model=list[schemas.EventResponse])
def list_active_events(limit: int = Query(default=300, ge=1, le=2000), db: Session = Depends(get_db)):
    events = (
        db.query(EventDB)
        .filter(EventDB.status == "active")
        .order_by(EventDB.start_datetime.desc())
        .limit(limit)
        .all()
    )
    out = []
    for ev in events:
        pred = _latest_prediction(db, ev.id)
        out.append(_event_db_to_response(ev, pred))
    return out


@router.get("/replay/stream", response_model=list[schemas.EventResponse])
def replay_stream(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """
    Returns a chronologically-ordered slice of historical events for the
    frontend's accelerated replay mode (roadmap 8.1) — the frontend is
    expected to page through this with increasing `offset` on a timer.
    """
    events = (
        db.query(EventDB)
        .filter(EventDB.is_simulated == False)  # noqa: E712
        .order_by(EventDB.start_datetime.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [_event_db_to_response(ev, _latest_prediction(db, ev.id)) for ev in events]


@router.get("/{event_id}", response_model=schemas.EventResponse)
def get_event(event_id: str, db: Session = Depends(get_db)):
    ev = db.query(EventDB).filter(EventDB.id == event_id).first()
    if ev is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return _event_db_to_response(ev, _latest_prediction(db, event_id))


@router.get("/{event_id}/response-card", response_model=schemas.EventResponseCard)
def get_response_card(event_id: str, db: Session = Depends(get_db)):
    """Builds (or reuses the latest cached) full Event Response Card for an existing DB event."""
    _require_predictor_ready()
    ev = db.query(EventDB).filter(EventDB.id == event_id).first()
    if ev is None:
        raise HTTPException(status_code=404, detail="Event not found")

    event_dict = _event_db_to_dict(ev)
    event_dict["junction_norm"] = data_cleaning.normalize_junction(ev.junction)

    pred_row = _latest_prediction(db, event_id)
    if pred_row is None:
        prediction = predictor.predict_event(event_dict, event_id=event_id)
        pred_row = _persist_prediction(db, prediction)
    else:
        prediction = {
            "event_id": pred_row.event_id,
            "severity": pred_row.severity,
            "severity_confidence": pred_row.severity_confidence,
            "closure_probability": pred_row.closure_probability,
            "duration_median_mins": pred_row.duration_median_mins,
            "duration_lower_mins": pred_row.duration_lower_mins,
            "duration_upper_mins": pred_row.duration_upper_mins,
            "predicted_at": pred_row.predicted_at,
        }

    concurrent = (
        db.query(func.count(EventDB.id))
        .filter(EventDB.police_station == ev.police_station, EventDB.status == "active")
        .scalar()
        if ev.police_station else None
    )

    extras = build_response_card(
        event=event_dict, prediction=prediction, concurrent_active_in_station=concurrent
    )

    return {
        "event": _event_db_to_response(ev, pred_row),
        "prediction": prediction,
        "manpower": extras["manpower"],
        "barricade": extras["barricade"],
        "diversion": extras["diversion"],
    }


@router.post("/feedback")
def submit_feedback(payload: schemas.FeedbackRequest, db: Session = Depends(get_db)):
    """
    Post-event ground truth logging — the minimal version of the
    "no post-event learning system" gap closure (roadmap module 6 /
    section 10). Appends to the feedback table; a periodic batch job (or
    the `retrain` CLI script) would later fold this into the next
    training run.
    """
    ev = db.query(EventDB).filter(EventDB.id == payload.event_id).first()
    if ev is None:
        raise HTTPException(status_code=404, detail="Event not found")

    row = FeedbackDB(
        event_id=payload.event_id,
        actual_duration_mins=payload.actual_duration_mins,
        actual_closure_needed=payload.actual_closure_needed,
        actual_severity=payload.actual_severity,
        officers_deployed=payload.officers_deployed,
        notes=payload.notes,
    )
    db.add(row)

    if payload.actual_closure_needed is not None:
        ev.requires_road_closure = payload.actual_closure_needed
    ev.status = "resolved"
    ev.resolved_datetime = datetime.now(timezone.utc)
    db.commit()

    return {"status": "logged", "feedback_id": row.id, "event_id": payload.event_id}
