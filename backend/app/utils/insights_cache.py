"""
Insights cache — precomputes the EDA-grade aggregate tables from roadmap
section 3 once, at startup, from the processed historical dataset (the
parquet file written by scripts/preprocess.py). These power the dashboard's
"Insights" screen (roadmap section 9, Screen 4) and are deliberately kept
separate from the live `events` DB table, since that table also accumulates
what-if/simulated events which should never quietly skew the dataset-level
EDA charts a judge will see.
"""
from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from app.config import settings
from app.utils import time_utils

logger = logging.getLogger("vyuha.insights")


class InsightsCache:
    def __init__(self):
        self.df: Optional[pd.DataFrame] = None
        self.loaded: bool = False
        self.load_error: Optional[str] = None

    def load(self) -> "InsightsCache":
        try:
            self.df = pd.read_parquet(settings.PROCESSED_DATA_FILE)
            self.loaded = True
            self.load_error = None
            logger.info("InsightsCache: loaded %d processed events.", len(self.df))
        except FileNotFoundError as e:
            self.loaded = False
            self.load_error = (
                f"Processed dataset not found ({e}). Run `python scripts/preprocess.py` first."
            )
            logger.warning(self.load_error)
        return self

    # ── Summary ──────────────────────────────────────────────────────────────

    def summary(self) -> dict:
        df = self.df
        starts = df["start_dt"].dropna()
        return {
            "total_events": int(len(df)),
            "active_events": int((df["status"] == "active").sum()) if "status" in df.columns else 0,
            "planned_count": int((df["event_type"] == "planned").sum()),
            "unplanned_count": int((df["event_type"] != "planned").sum()),
            "date_range_start": starts.min().isoformat() if len(starts) else None,
            "date_range_end": starts.max().isoformat() if len(starts) else None,
            "unique_corridors": int(df["corridor"].nunique()) if "corridor" in df.columns else 0,
            "unique_junctions": int(df["junction_norm"].nunique()) if "junction_norm" in df.columns else 0,
            "unique_police_stations": int(df["police_station"].nunique()) if "police_station" in df.columns else 0,
            "road_closure_rate_pct": round(float(df["requires_road_closure"].mean()) * 100, 2),
        }

    # ── Hourly pattern (the headline curfew / 2 AM insight) ────────────────────

    def hourly_pattern(self) -> list[dict]:
        df = self.df.copy()
        df["hour_ist"] = df["start_dt"].apply(time_utils.hour_ist)
        counts = df["hour_ist"].value_counts().reindex(range(24), fill_value=0).sort_index()
        points = []
        for hour, count in counts.items():
            is_curfew = time_utils.is_curfew_window(int(hour))
            label = f"{hour:02d}:00"
            points.append({
                "hour": int(hour),
                "count": int(count),
                "is_curfew_window": bool(is_curfew),
                "label": label,
            })
        return points

    # ── Per-cause breakdown ─────────────────────────────────────────────────

    def cause_stats(self) -> list[dict]:
        df = self.df
        total = len(df)
        rows = []
        grouped = df.groupby("event_cause")
        for cause, g in grouped:
            observed = g[g["observed"] == 1]["duration_mins"] if "observed" in g.columns else pd.Series(dtype=float)
            rows.append({
                "cause": cause,
                "count": int(len(g)),
                "share_pct": round(len(g) / total * 100, 2) if total else 0.0,
                "median_duration_mins": round(float(observed.median()), 1) if len(observed) else None,
                "closure_rate_pct": round(float(g["requires_road_closure"].mean()) * 100, 2),
            })
        rows.sort(key=lambda r: r["count"], reverse=True)
        return rows

    # ── Per-corridor breakdown ──────────────────────────────────────────────

    def corridor_stats(self, top_n: int = 15) -> list[dict]:
        df = self.df
        rows = []
        for corridor, g in df.groupby("corridor"):
            high_pct = round(float((g["severity"] == "High").mean()) * 100, 2) if "severity" in g.columns else 0.0
            rows.append({
                "corridor": corridor,
                "count": int(len(g)),
                "high_severity_pct": high_pct,
                "avg_closure_rate": round(float(g["requires_road_closure"].mean()) * 100, 2),
            })
        rows.sort(key=lambda r: r["count"], reverse=True)
        return rows[:top_n]

    # ── Derived severity vs raw priority discrepancy ────────────────────────

    def severity_vs_priority(self) -> list[dict]:
        """
        Surfaces cases (e.g. tree_fall) where the raw manually-assigned
        `priority` field and our ML-derived composite `severity` disagree —
        the concrete "we add value over the status quo" evidence from
        roadmap sections 3.4 / 6.1 / 14.
        """
        df = self.df
        rows = []
        for cause, g in df.groupby("event_cause"):
            if "priority" not in g.columns or "severity" not in g.columns:
                continue
            valid = g[g["priority"].notna()]
            if len(valid) == 0:
                continue
            raw_high_pct = round(float((valid["priority"] == "High").mean()) * 100, 2)
            ml_high_pct = round(float((g["severity"] == "High").mean()) * 100, 2)
            closure_pct = round(float(g["requires_road_closure"].mean()) * 100, 2)
            gap = abs(raw_high_pct - ml_high_pct)
            discrepancy = gap >= 15.0
            if discrepancy:
                note = (
                    f"Raw priority marks this cause High {raw_high_pct}% of the time, but our derived "
                    f"severity (which also weighs the {closure_pct}% closure rate) marks it High "
                    f"{ml_high_pct}% of the time — a {gap:.0f}-point gap worth flagging to operators."
                )
            else:
                note = "Raw priority and derived severity broadly agree for this cause."
            rows.append({
                "cause": cause,
                "count": int(len(g)),
                "raw_priority_high_pct": raw_high_pct,
                "ml_severity_high_pct": ml_high_pct,
                "closure_rate_pct": closure_pct,
                "note": note,
                "discrepancy": discrepancy,
            })
        rows.sort(key=lambda r: r["count"], reverse=True)
        return rows


# Module-level singleton, populated at FastAPI startup (see app/main.py)
insights_cache = InsightsCache()
