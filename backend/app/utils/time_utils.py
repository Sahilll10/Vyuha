"""
Timezone and temporal helper functions.

CRITICAL: every timestamp in the raw ASTraM CSV is UTC. All downstream
temporal features (hour-of-day, curfew window, etc.) must be derived from
IST, or the headline "2 AM breakdown spike" insight silently shifts by
5h30m and becomes wrong without raising an error. Every hour-of-day
feature in this codebase MUST go through `to_ist` first.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd

from app.config import settings

IST = timezone(timedelta(hours=settings.IST_OFFSET_HOURS, minutes=settings.IST_OFFSET_MINUTES))


def parse_utc(value) -> Optional[pd.Timestamp]:
    """Parse a raw timestamp string/value as a UTC-aware pandas Timestamp."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    ts = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(ts):
        return None
    return ts


def to_ist(ts) -> Optional[pd.Timestamp]:
    """Convert a UTC-aware timestamp (or anything pandas can parse) to IST."""
    if ts is None:
        return None
    if not isinstance(ts, pd.Timestamp):
        ts = parse_utc(ts)
        if ts is None:
            return None
    if pd.isna(ts):
        return None
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return ts.tz_convert(IST)


def hour_ist(ts) -> Optional[int]:
    ist = to_ist(ts)
    return None if ist is None else int(ist.hour)


def is_curfew_window(hour: Optional[int]) -> bool:
    """
    True if `hour` (0-23, IST) falls in Bengaluru's heavy-vehicle entry
    window (22:00 - 07:00), i.e. the window during which goods vehicles
    above ~3T are legally allowed on city roads. This is the feature that
    explains the dataset's 2-4 AM breakdown spike.
    """
    if hour is None:
        return False
    start, end = settings.CURFEW_ALLOWED_START, settings.CURFEW_ALLOWED_END
    if start > end:  # window wraps past midnight, e.g. 22 -> 7
        return hour >= start or hour < end
    return start <= hour < end


def day_of_week_ist(ts) -> Optional[int]:
    """Monday=0 ... Sunday=6, in IST."""
    ist = to_ist(ts)
    return None if ist is None else int(ist.dayofweek)


def is_weekend_ist(ts) -> bool:
    dow = day_of_week_ist(ts)
    return dow is not None and dow >= 5


def month_ist(ts) -> Optional[int]:
    ist = to_ist(ts)
    return None if ist is None else int(ist.month)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
