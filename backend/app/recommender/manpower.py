"""
Manpower allocation — roadmap section 7.1.

Two layers:
  1. `recommend_manpower` — a single-incident lookup: severity x cause ->
     headcount range, with a supervisor flag for the highest-stakes causes.
  2. `allocate_station_resources` — a deployment-aware greedy allocator
     across *multiple concurrent* active incidents in one station's
     jurisdiction (very realistic: the historical data shows ~1,000 events
     were "active" at any given snapshot). Sorts by predicted severity and
     assigns available officers in priority order, flagging when total
     demand exceeds what the station typically fields.

A formal linear-program version (maximize weighted severity coverage
subject to a headcount constraint, via PuLP) is a natural upgrade if time
allows — the greedy version here is the deliberately simple baseline the
roadmap recommends shipping first.
"""
from __future__ import annotations

from typing import List, Optional

# Base officer count by severity, before cause-specific modifiers.
_BASE_COUNT = {"Low": 1, "Medium": 2, "High": 4}

# Causes that warrant a supervisor present regardless of severity tier,
# and an extra officer or two on top of the base count — these are exactly
# the "festivals and rallies" cases the problem statement leads with.
_CAUSE_MODIFIERS = {
    "vip_movement": {"extra_officers": 2, "supervisor": True},
    "public_event": {"extra_officers": 2, "supervisor": True},
    "protest": {"extra_officers": 2, "supervisor": True},
    "procession": {"extra_officers": 1, "supervisor": True},
    "tree_fall": {"extra_officers": 1, "supervisor": False},
    "construction": {"extra_officers": 0, "supervisor": False},
    "accident": {"extra_officers": 1, "supervisor": False},
}
_DEFAULT_MODIFIER = {"extra_officers": 0, "supervisor": False}

_UNIT_LIBRARY = {
    "Low": ["1 traffic constable"],
    "Medium": ["2 traffic constables", "1 home guard"],
    "High": ["1 sub-inspector / supervisor", "3-4 traffic constables", "2 home guards"],
}


def recommend_manpower(
    severity: str,
    event_cause: str,
    requires_road_closure: bool,
    concurrent_active_in_station: Optional[int] = None,
) -> dict:
    base = _BASE_COUNT.get(severity, 1)
    mod = _CAUSE_MODIFIERS.get(event_cause, _DEFAULT_MODIFIER)

    officers = base + mod["extra_officers"]
    if requires_road_closure:
        officers += 1  # someone has to physically staff the closure point

    supervisor_required = mod["supervisor"] or severity == "High"

    units = list(_UNIT_LIBRARY.get(severity, _UNIT_LIBRARY["Low"]))
    if requires_road_closure and "Barricade detail (2 constables)" not in units:
        units.append("Barricade detail (2 constables)")

    rationale_parts = [f"{severity} severity {event_cause.replace('_', ' ')} event"]
    if requires_road_closure:
        rationale_parts.append("requires a full road closure")
    if mod["supervisor"]:
        rationale_parts.append("cause type warrants on-site supervision")
    rationale = "; ".join(rationale_parts) + f" -> recommend {officers} officer(s)."

    capacity_warning = None
    if concurrent_active_in_station is not None and concurrent_active_in_station >= 6:
        capacity_warning = (
            f"This station is already handling {concurrent_active_in_station} active "
            "incidents — confirm available headcount before dispatching."
        )

    return {
        "officers": officers,
        "supervisor_required": supervisor_required,
        "units": units,
        "rationale": rationale,
        "capacity_warning": capacity_warning,
    }


_SEVERITY_RANK = {"High": 3, "Medium": 2, "Low": 1}


def allocate_station_resources(events: List[dict], station_capacity: int) -> dict:
    """
    Simple greedy allocator across concurrent active incidents at one
    station. `events` is a list of dicts with at least
    {event_id, severity, recommended_officers}. Returns the assignment
    order, total demand, and whether the station is over capacity.
    """
    ranked = sorted(
        events,
        key=lambda e: (_SEVERITY_RANK.get(e.get("severity", "Low"), 1), e.get("recommended_officers", 0)),
        reverse=True,
    )

    assigned, remaining = [], station_capacity
    for e in ranked:
        need = e.get("recommended_officers", 1)
        granted = min(need, remaining)
        assigned.append({
            "event_id": e.get("event_id"),
            "severity": e.get("severity"),
            "officers_needed": need,
            "officers_granted": granted,
            "fully_covered": granted >= need,
        })
        remaining = max(0, remaining - granted)

    total_demand = sum(e.get("recommended_officers", 1) for e in events)
    return {
        "assignments": assigned,
        "total_demand": total_demand,
        "station_capacity": station_capacity,
        "shortfall": max(0, total_demand - station_capacity),
        "over_capacity": total_demand > station_capacity,
    }
