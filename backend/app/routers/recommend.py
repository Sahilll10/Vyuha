"""
/recommend — standalone access to each prescriptive module (roadmap
section 7), independent of the full Event Response Card. Useful for the
frontend's individual widgets (e.g. re-running just the diversion routing
after a barricade plan is manually adjusted) and for judges who want to
probe each module in isolation via /docs.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.models import schemas
from app.recommender.barricade import recommend_barricades
from app.recommender.manpower import allocate_station_resources, recommend_manpower
from app.recommender.routing import road_graph

router = APIRouter(prefix="/recommend", tags=["recommend"])


@router.post("/manpower", response_model=schemas.ManpowerResponse)
def recommend_manpower_endpoint(payload: schemas.ManpowerRequest):
    return recommend_manpower(
        severity=payload.severity,
        event_cause=payload.event_cause,
        requires_road_closure=payload.requires_road_closure,
        concurrent_active_in_station=payload.concurrent_active_in_station,
    )


@router.post("/barricade", response_model=schemas.BarricadeResponse)
def recommend_barricade_endpoint(payload: schemas.BarricadeRequest):
    return recommend_barricades(
        latitude=payload.latitude,
        longitude=payload.longitude,
        event_cause=payload.event_cause,
        requires_road_closure=payload.requires_road_closure,
        endlatitude=payload.endlatitude,
        endlongitude=payload.endlongitude,
        corridor=payload.corridor,
        address=payload.address,
    )


@router.post("/diversion", response_model=schemas.DiversionResponse)
def recommend_diversion_endpoint(payload: schemas.DiversionRequest):
    return road_graph.suggest_diversions(
        payload.latitude, payload.longitude, max_routes=payload.max_routes
    )


@router.post("/station-allocation", response_model=schemas.StationAllocationResponse)
def station_allocation_endpoint(payload: schemas.StationAllocationRequest):
    return allocate_station_resources(payload.events, payload.station_capacity)
