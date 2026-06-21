"""
/predict — direct access to the predictive impact engine (roadmap section 6),
decoupled from the recommendation engine. Useful for judges/devs who want to
see raw model output, and for the frontend's lighter-weight "just show me
the forecast" calls that don't need a full Response Card.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import EventDB, get_db
from app.models import schemas
from app.ml.predictor import predictor
from app.utils import data_cleaning

router = APIRouter(prefix="/predict", tags=["predict"])


def _require_predictor_ready():
    if not predictor.loaded:
        raise HTTPException(
            status_code=503,
            detail=predictor.load_error or "Models are not loaded yet. Train and restart the API.",
        )


@router.post("/event", response_model=schemas.PredictionResponse)
def predict_unscored_event(payload: schemas.EventCreateRequest):
    """Score a brand-new event without writing anything to the database."""
    _require_predictor_ready()
    event_dict = payload.model_dump()
    event_dict["junction_norm"] = data_cleaning.normalize_junction(payload.junction)
    prediction = predictor.predict_event(event_dict, event_id="unscored")
    return prediction


@router.post("/event/{event_id}", response_model=schemas.PredictionResponse)
def predict_existing_event(event_id: str, db: Session = Depends(get_db)):
    """Score an existing DB event and persist the prediction."""
    _require_predictor_ready()
    ev = db.query(EventDB).filter(EventDB.id == event_id).first()
    if ev is None:
        raise HTTPException(status_code=404, detail="Event not found")

    event_dict = {
        "latitude": ev.latitude,
        "longitude": ev.longitude,
        "event_cause": ev.event_cause,
        "event_type": ev.event_type,
        "start_datetime": ev.start_datetime,
        "corridor": ev.corridor,
        "police_station": ev.police_station,
        "zone": ev.zone,
        "veh_type": ev.veh_type,
        "junction": ev.junction,
        "junction_norm": data_cleaning.normalize_junction(ev.junction),
        "description": ev.description,
    }
    prediction = predictor.predict_event(event_dict, event_id=event_id)

    from app.database import PredictionDB
    row = PredictionDB(
        event_id=event_id,
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

    return prediction
