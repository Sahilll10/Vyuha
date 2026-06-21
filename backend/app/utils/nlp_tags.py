"""
Lightweight multilingual keyword tagger for `description` / `comment`.

The field-reported description text mixes English, Kannada (Kannada
script), typos, and operational shorthand (e.g. "tyre blast 15 min towing
will remove"). Rather than dropping non-English rows (what most teams will
do), we tag a small set of high-value operational signals with cheap
keyword/regex matching. This is intentionally simple — option 1 from the
roadmap's section 3.7 — and is meant to feed auxiliary boolean features
into the tabular model, not to do full NLU.

Extending to multilingual sentence embeddings (roadmap option 2) is a
clean drop-in: swap `tag_description` for an embedding lookup and feed
the vector into the same feature slot.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

# Keyword groups: English + common transliterations/shorthand seen in the
# field data. Kannada-script keywords are matched as literal substrings
# (regex on raw text), since Kannada script doesn't need tokenization the
# way romanized text does for this kind of coarse tagging.
_TOWING_KEYWORDS = [
    "towing", "tow truck", "crane", "recovery van", "ಎಳೆಯುವ",
]
_RESOLUTION_IN_PROGRESS_KEYWORDS = [
    "mechanic", "mechanic arrived", "will remove", "being cleared",
    "clearing", "in progress", "on the way", "minutes towing",
]
_CLEARED_KEYWORDS = [
    "cleared", "removed", "resolved", "normal now", "traffic normal",
    "ತೆರವು",
]
_FIRE_KEYWORDS = ["fire", "burning", "smoke", "ಬೆಂಕಿ"]
_MINOR_KEYWORDS = ["minor", "small", "no major issue", "not serious"]
_SEVERE_KEYWORDS = [
    "major", "serious", "casualty", "casualties", "injured", "injury",
    "fatal", "death", "ambulance",
]

NLP_FLAG_COLUMNS = [
    "mentions_towing", "mentions_resolution_in_progress", "mentions_cleared",
    "mentions_fire", "mentions_minor", "mentions_severe", "has_description",
]


def _contains_any(text: str, keywords) -> bool:
    return any(kw in text for kw in keywords)


def tag_description(text: Optional[str]) -> dict:
    """
    Returns a dict of boolean flags derived from free-text description.
    Safe on None/NaN/empty/non-English/Kannada text.
    """
    flags = {col: False for col in NLP_FLAG_COLUMNS}
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return flags
    raw = str(text).strip()
    if not raw:
        return flags

    flags["has_description"] = True
    lowered = raw.lower()
    flags["mentions_towing"] = _contains_any(lowered, _TOWING_KEYWORDS) or _contains_any(raw, _TOWING_KEYWORDS)
    flags["mentions_resolution_in_progress"] = _contains_any(lowered, _RESOLUTION_IN_PROGRESS_KEYWORDS)
    flags["mentions_cleared"] = _contains_any(lowered, _CLEARED_KEYWORDS) or _contains_any(raw, _CLEARED_KEYWORDS)
    flags["mentions_fire"] = _contains_any(lowered, _FIRE_KEYWORDS) or _contains_any(raw, _FIRE_KEYWORDS)
    flags["mentions_minor"] = _contains_any(lowered, _MINOR_KEYWORDS)
    flags["mentions_severe"] = _contains_any(lowered, _SEVERE_KEYWORDS)
    return flags
