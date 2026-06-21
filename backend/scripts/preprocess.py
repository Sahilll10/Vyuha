"""
scripts/preprocess.py

Run from the `backend/` directory:
    python scripts/preprocess.py

Reads the raw ASTraM CSV (settings.RAW_DATA_FILE), applies all cleaning
steps from roadmap section 3/5 (timezone-safe parsing, cause/junction/
priority/veh_type normalization, the 0.0-coordinate sentinel fix, H3
spatial indexing), computes the censoring-aware duration label and the
composite severity label, and writes the result to
settings.PROCESSED_DATA_FILE (parquet).

This processed file is the single shared input for:
  - scripts/train_models.py        (feature engineering + model training)
  - app.utils.insights_cache        (the dashboard's Insights screen)
  - app.main._build_junctions_df_for_fallback_graph (offline routing graph)
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow running as `python scripts/preprocess.py` from the backend/ root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from app.config import settings  # noqa: E402
from app.utils import data_loading  # noqa: E402


def main():
    print("=" * 60)
    print("VYUHA — preprocessing raw ASTraM events")
    print("=" * 60)

    raw_path = settings.RAW_DATA_FILE
    print(f"\n[1/4] Loading raw CSV from {raw_path} ...")
    raw = data_loading.load_raw_csv(raw_path)
    print(f"      {len(raw):,} raw rows, {len(raw.columns)} columns.")

    print("\n[2/4] Cleaning + normalizing fields (timezone, causes, junctions, coords) ...")
    cleaned = data_loading.clean_raw_events(raw)

    print("\n[3/4] Computing censoring-aware duration + composite severity label ...")
    with_duration = data_loading.compute_duration_and_censoring(cleaned)
    with_duration["severity"] = data_loading.build_severity_label(with_duration)

    n_observed = int(with_duration["observed"].sum())
    print(f"      {n_observed:,} / {len(with_duration):,} events have a true (non-censored) duration "
          f"({n_observed / len(with_duration) * 100:.1f}%).")
    print("      Severity label distribution:")
    print(with_duration["severity"].value_counts().to_string().replace("\n", "\n      "))

    print(f"\n[4/4] Writing processed dataset to {settings.PROCESSED_DATA_FILE} ...")
    Path(settings.PROCESSED_DATA_FILE).parent.mkdir(parents=True, exist_ok=True)
    with_duration.to_parquet(settings.PROCESSED_DATA_FILE, index=False)

    duration_subset = with_duration.loc[with_duration["observed"] == 1, ["event_cause", "duration_mins"]]
    Path(settings.DURATION_TRAIN_FILE).parent.mkdir(parents=True, exist_ok=True)
    duration_subset.to_parquet(settings.DURATION_TRAIN_FILE, index=False)
    print(f"      Non-censored duration subset ({len(duration_subset):,} rows) written to "
          f"{settings.DURATION_TRAIN_FILE}.")

    # ── A quick console echo of the headline EDA numbers (roadmap section 3) ──
    print("\n" + "-" * 60)
    print("Quick sanity-check numbers (compare against roadmap section 3):")
    print("-" * 60)
    print(f"Total events:           {len(with_duration):,}")
    print(f"Unplanned / Planned:    {(with_duration['event_type'] != 'planned').sum():,} / "
          f"{(with_duration['event_type'] == 'planned').sum():,}")
    print(f"Road closure rate:      {with_duration['requires_road_closure'].mean() * 100:.1f}%")
    print(f"Unique corridors:       {with_duration['corridor'].nunique()}")
    print(f"Unique junctions (norm): {with_duration['junction_norm'].nunique()}")
    print(f"Median duration (obs):  {with_duration.loc[with_duration['observed'] == 1, 'duration_mins'].median():.1f} min")
    print("\nDone. Next: python scripts/train_models.py")


if __name__ == "__main__":
    main()
