"""
Geospatial helper functions: H3 hex indexing (for bucketing the 294 messy
junction strings into clean, consistent spatial cells) and haversine
distance / bearing math (for recurrence features and barricade-offset
geometry).

Uses the h3 v4 API (latlng_to_cell / cell_to_latlng / grid_disk), which is
what's pinned in requirements.txt. If you're on h3 v3.x, the equivalent
calls are geo_to_h3 / h3_to_geo / k_ring — see `_H3_V4` below for the
compatibility shim.
"""
from __future__ import annotations

import math
from typing import Optional

from app.config import settings

try:
    import h3
    _H3_V4 = hasattr(h3, "latlng_to_cell")
except ImportError:  # pragma: no cover
    h3 = None
    _H3_V4 = False


def to_h3(lat: Optional[float], lng: Optional[float], resolution: int = None) -> Optional[str]:
    if lat is None or lng is None or h3 is None:
        return None
    try:
        res = resolution or settings.H3_RESOLUTION
        if _H3_V4:
            return h3.latlng_to_cell(float(lat), float(lng), res)
        return h3.geo_to_h3(float(lat), float(lng), res)  # h3 v3.x fallback
    except Exception:
        return None


def h3_neighbors(cell: str, k: int = 1):
    """All H3 cells within k rings of `cell` (inclusive of `cell` itself)."""
    if not cell or h3 is None:
        return [cell] if cell else []
    try:
        if _H3_V4:
            return list(h3.grid_disk(cell, k))
        return list(h3.k_ring(cell, k))  # h3 v3.x fallback
    except Exception:
        return [cell]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometers."""
    R = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(min(1.0, math.sqrt(a)))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial compass bearing in degrees (0=N, 90=E) from point 1 to point 2."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)
    x = math.sin(dlambda) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dlambda)
    theta = math.atan2(x, y)
    return (math.degrees(theta) + 360) % 360


def offset_point(lat: float, lon: float, distance_km: float, bearing_degrees: float):
    """Project a new (lat, lon) `distance_km` away from (lat, lon) along `bearing_degrees`."""
    R = 6371.0088
    brng = math.radians(bearing_degrees)
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    d_r = distance_km / R
    lat2 = math.asin(
        math.sin(lat1) * math.cos(d_r) + math.cos(lat1) * math.sin(d_r) * math.cos(brng)
    )
    lon2 = lon1 + math.atan2(
        math.sin(brng) * math.sin(d_r) * math.cos(lat1),
        math.cos(d_r) - math.sin(lat1) * math.sin(lat2),
    )
    return math.degrees(lat2), math.degrees(lon2)


def in_bengaluru_bbox(lat: float, lon: float) -> bool:
    return settings.LAT_MIN <= lat <= settings.LAT_MAX and settings.LNG_MIN <= lon <= settings.LNG_MAX
