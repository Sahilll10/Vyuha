"""
scripts/retrain_from_feedback.py

Run from the `backend/` directory:
    python scripts/retrain_from_feedback.py

The minimal, honest version of the "no post-event learning system" gap
closure (roadmap section 10). Pulls every row logged via POST
/events/feedback, folds the corrected outcomes (actual duration / actual
closure-needed / actual severity) back into the processed training frame
in place of the original (possibly censored or wrong) values, and re-runs
the full training pipeline on the combined dataset.

This does not run on a schedule — for a one-week hackathon demo, a
"Retrain now" button on the dashboard calling this script (or an
equivalent `/admin/retrain` endpoint, left as a clearly-labeled future
extension in the README) is enough to prove the loop is real, without
the added complexity of real scheduling infrastructure.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import FeedbackDB, SessionLocal  # noqa: E402
from scripts.train_models import main as train_main  # noqa: E402


def fold_feedback_into_processed_dataset() -> int:
    db = SessionLocal()
    try:
        feedback_rows = db.query(FeedbackDB).all()
    finally:
        db.close()

    if not feedback_rows:
        print("No feedback rows logged yet — nothing to fold in. Run training as-is.")
        return 0

    df = pd.read_parquet(settings.PROCESSED_DATA_FILE)
    df = df.set_index("id", drop=False)

    n_updated = 0
    for fb in feedback_rows:
        if fb.event_id not in df.index:
            continue  # feedback for a what-if/simulated event not in the historical frame
        if fb.actual_duration_mins is not None:
            df.loc[fb.event_id, "duration_mins"] = min(fb.actual_duration_mins, settings.DURATION_CAP_MINS)
            df.loc[fb.event_id, "observed"] = 1
        if fb.actual_closure_needed is not None:
            df.loc[fb.event_id, "requires_road_closure"] = bool(fb.actual_closure_needed)
        if fb.actual_severity is not None:
            df.loc[fb.event_id, "severity"] = fb.actual_severity
        n_updated += 1

    df = df.reset_index(drop=True)
    df.to_parquet(settings.PROCESSED_DATA_FILE, index=False)

    duration_subset = df.loc[df["observed"] == 1, ["event_cause", "duration_mins"]]
    duration_subset.to_parquet(settings.DURATION_TRAIN_FILE, index=False)

    print(f"Folded {n_updated} feedback record(s) into the processed dataset.")
    return n_updated


if __name__ == "__main__":
    print("=" * 60)
    print("VYUHA — retraining from post-event feedback")
    print("=" * 60)
    fold_feedback_into_processed_dataset()
    print("\nRe-running the full training pipeline on the updated dataset...\n")
    train_main()
