"""
Data cleaning helpers for the raw ASTraM export.

The raw CSV has a handful of well-known quirks (see roadmap section 3):
  - event_cause has inconsistent casing ('Debris' vs 'debris') and a few
    near-singleton categories (test_demo, 'Fog / Low Visibility') that are
    too rare to model on their own and get folded into 'others'.
  - junction is free text with mixed casing and stray parentheticals.
  - endlatitude / endlongitude use 0.0 as a "not applicable" sentinel, not
    a literal coordinate near (0, 0) in the Gulf of Guinea.
"""
from __future__ import annotations

import re
from typing import Optional

import pandas as pd

# Canonical cause vocabulary — must match app.models.schemas.EventCauseEnum
_CANONICAL_CAUSES = {
    "vehicle_breakdown", "accident", "pot_holes", "construction",
    "water_logging", "tree_fall", "road_conditions", "congestion",
    "public_event", "procession", "vip_movement", "protest", "debris",
    "others",
}

# Raw -> canonical mapping for known variants / typos / casing issues
_CAUSE_ALIASES = {
    "debris": "debris",
    "test_demo": "others",
    "fog / low visibility": "others",
    "fog_low_visibility": "others",
    "processcion": "procession",   # observed typo variant in some exports
}


def normalize_event_cause(raw: Optional[str]) -> str:
    """Map any raw event_cause value to the canonical lowercase vocabulary."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return "others"
    key = str(raw).strip().lower()
    if key in _CANONICAL_CAUSES:
        return key
    if key in _CAUSE_ALIASES:
        return _CAUSE_ALIASES[key]
    # Anything else unseen (future-proofing for live feeds) buckets to "others"
    return "others"


def normalize_priority(raw: Optional[str]) -> Optional[str]:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    key = str(raw).strip().lower()
    if key.startswith("high"):
        return "High"
    if key.startswith("low"):
        return "Low"
    return None


def normalize_veh_type(raw: Optional[str]) -> str:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return "unknown"
    val = str(raw).strip().lower().replace(" ", "_")
    return val or "unknown"


_PAREN_RE = re.compile(r"\([^)]*\)")
_WS_RE = re.compile(r"\s+")


def normalize_junction(raw: Optional[str]) -> Optional[str]:
    """
    Normalize the messy `junction` free-text field: strip parentheticals,
    collapse whitespace, and case-fold to a consistent form so that
    'silkboardjunc', 'SilkBoardJunc', 'SilkBoard Junc ' all collapse to the
    same category instead of being treated as distinct junctions.
    """
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    text = str(raw)
    text = _PAREN_RE.sub("", text)
    text = _WS_RE.sub(" ", text).strip()
    if not text:
        return None
    return text.lower()


def clean_end_coordinate(value) -> Optional[float]:
    """Treat the 0.0 sentinel used for 'not applicable' as missing."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        fval = float(value)
    except (TypeError, ValueError):
        return None
    if abs(fval) < 1e-6:
        return None
    return fval


def normalize_status(raw: Optional[str]) -> str:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return "closed"
    key = str(raw).strip().lower()
    if key in {"active", "closed", "resolved"}:
        return key
    return "closed"
