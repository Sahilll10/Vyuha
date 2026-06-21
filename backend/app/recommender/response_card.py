"""
The Event Response Card — roadmap section 7.4.

This is the single most demo-able artifact in the whole system: every time
an event is forecast, this function produces one unified payload —
predicted severity, expected duration with a confidence range, road-closure
probability, recommended manpower, recommended barricade points, and 2-3
ranked diversion routes — all generated, not hand-waved. Routers call this
one function rather than re-assembling the four pieces themselves.
"""
from __future__ import annotations

from typing import Optional

from app.recommender.barricade import recommend_barricades
from app.recommender.manpower import recommend_manpower
from app.recommender.routing import road_graph


def build_response_card(
    event: dict,
    prediction: dict,
    concurrent_active_in_station: Optional[int] = None,
    max_routes: int = 3,
) -> dict:
    """
    event: cleaned event dict (latitude, longitude, endlatitude,
        endlongitude, event_cause, corridor, address, ...)
    prediction: output of app.ml.predictor.Predictor.predict_event(), i.e.
        {severity, closure_probability, duration_median_mins, ...}

    The closure DECISION used to drive barricade/diversion logic is the
    *predicted* probability thresholded at 0.5 for a what-if/unscored
    event, but falls back to the event's own ground-truth
    `requires_road_closure` flag when present (historical/replayed events
    already know the real answer and there's no reason to second-guess it
    on the dashboard).
    """
    if "requires_road_closure" in event and event["requires_road_closure"] is not None:
        requires_closure = bool(event["requires_road_closure"])
    else:
        requires_closure = prediction["closure_probability"] >= 0.5

    manpower = recommend_manpower(
        severity=prediction["severity"],
        event_cause=event["event_cause"],
        requires_road_closure=requires_closure,
        concurrent_active_in_station=concurrent_active_in_station,
    )

    barricade = recommend_barricades(
        latitude=event["latitude"],
        longitude=event["longitude"],
        event_cause=event["event_cause"],
        requires_road_closure=requires_closure,
        endlatitude=event.get("endlatitude"),
        endlongitude=event.get("endlongitude"),
        corridor=event.get("corridor"),
        address=event.get("address"),
    )

    if requires_closure and road_graph.is_ready:
        diversion = road_graph.suggest_diversions(
            event["latitude"], event["longitude"], max_routes=max_routes
        )
    elif not requires_closure:
        diversion = {
            "routes": [],
            "baseline_distance_km": None,
            "routing_mode": road_graph.mode or "fallback",
            "note": "No road closure expected — diversion routing not triggered for this event.",
        }
    else:
        diversion = {
            "routes": [],
            "baseline_distance_km": None,
            "routing_mode": "unavailable",
            "note": "Road graph has not finished loading yet — try again shortly.",
        }

    return {
        "manpower": manpower,
        "barricade": barricade,
        "diversion": diversion,
    }
