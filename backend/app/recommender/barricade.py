"""
Barricade placement — roadmap section 7.2.

Decides whether a barricade is needed at all (driven by `requires_road_closure`,
either the ground-truth field for a historical event or the closure model's
prediction for a what-if event), what kind, and where — output as a short,
human-readable instruction plus coordinates the frontend can drop pins on.

For point events (no end coordinate — the vast majority of the dataset),
barricade points are generated ~150m upstream of the incident on each
approach, offset using the haversine bearing math in app.utils.geo_utils.
For linear events (procession routes, a fallen tree blocking a stretch —
when an end coordinate is present), barricades go at the start and end of
the affected stretch instead.
"""
from __future__ import annotations

from typing import Optional

from app.utils import geo_utils

_BARRICADE_OFFSET_KM = 0.15  # ~150m, matches the roadmap's example instruction


def recommend_barricades(
    latitude: float,
    longitude: float,
    event_cause: str,
    requires_road_closure: bool,
    endlatitude: Optional[float] = None,
    endlongitude: Optional[float] = None,
    corridor: Optional[str] = None,
    address: Optional[str] = None,
) -> dict:
    location_label = corridor or address or "the incident location"
    is_linear = endlatitude is not None and endlongitude is not None

    if not requires_road_closure:
        points = [{
            "latitude": latitude,
            "longitude": longitude,
            "label": "Advisory cone/flag point",
            "instruction": (
                f"No full closure expected — place a cone-and-flag warning at "
                f"the incident point on {location_label} and direct traffic around it."
            ),
        }]
        return {
            "closure_required": False,
            "barricade_type": "cone_and_flag",
            "points": points,
            "summary": "Lane-level warning only; full barricade not required.",
        }

    if is_linear:
        bearing = geo_utils.bearing_deg(latitude, longitude, endlatitude, endlongitude)
        points = [
            {
                "latitude": latitude,
                "longitude": longitude,
                "label": "Barricade — stretch start",
                "instruction": (
                    f"Place barricade at the start of the affected stretch on {location_label}; "
                    f"divert traffic before this point."
                ),
            },
            {
                "latitude": endlatitude,
                "longitude": endlongitude,
                "label": "Barricade — stretch end",
                "instruction": (
                    f"Place barricade at the end of the affected stretch on {location_label}; "
                    f"reopen lane access beyond this point."
                ),
            },
        ]
        summary = (
            f"Linear closure on {location_label} "
            f"({geo_utils.haversine_km(latitude, longitude, endlatitude, endlongitude):.2f} km "
            f"affected) — barricade both ends, bearing ~{bearing:.0f} deg."
        )
        return {
            "closure_required": True,
            "barricade_type": "full_closure_linear",
            "points": points,
            "summary": summary,
        }

    # Point event requiring closure: barricade both approaches, ~150m upstream
    # each way (north/south approach as a sane default when the corridor's
    # true road bearing isn't available; app.recommender.routing can supply a
    # real road-graph bearing when the OSM graph is loaded).
    north_lat, north_lon = geo_utils.offset_point(latitude, longitude, _BARRICADE_OFFSET_KM, 0)
    south_lat, south_lon = geo_utils.offset_point(latitude, longitude, _BARRICADE_OFFSET_KM, 180)

    points = [
        {
            "latitude": north_lat,
            "longitude": north_lon,
            "label": "Barricade — northern approach",
            "instruction": (
                f"Place barricade ~150m north of {location_label}; "
                f"divert southbound-approaching traffic onto the nearest cross street."
            ),
        },
        {
            "latitude": south_lat,
            "longitude": south_lon,
            "label": "Barricade — southern approach",
            "instruction": (
                f"Place barricade ~150m south of {location_label}; "
                f"divert northbound-approaching traffic onto the nearest cross street."
            ),
        },
    ]
    return {
        "closure_required": True,
        "barricade_type": "full_closure_point",
        "points": points,
        "summary": f"Full closure at {location_label} — barricade both approaches ~150m out.",
    }
