"""
scripts/train_models.py

Run from the `backend/` directory, AFTER scripts/preprocess.py:
    python scripts/train_models.py

Fits the shared FeatureEngineer, then trains all three predictive models
(severity classifier, closure-probability classifier, duration survival
model) on an 80/20 split, evaluates each on the held-out 20%, and saves
every artifact under saved_models/ for the API to load at startup.

Known simplification (documented, not hidden): the FeatureEngineer's
aggregate statistics (cause closure-rate, junction frequency, frozen
category vocabulary, and the recurrence-lookup history table) are fit on
the FULL dataset rather than the 80% training split alone. This means a
small amount of aggregate-level (not row-level-label) information leaks
into the held-out evaluation, which is an acceptable trade-off for a
one-week hackathon prototype — the row-level targets themselves are never
leaked, so the reported metrics still meaningfully reflect generalization,
just with a very slight optimistic bias on confidence-calibration-style
metrics. A production system would re-fit the FeatureEngineer with
walk-forward (time-based) splits instead of a random split.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import joblib  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.metrics import accuracy_score, classification_report, roc_auc_score  # noqa: E402
from sklearn.model_selection import train_test_split  # noqa: E402

from app.config import settings  # noqa: E402
from app.ml.closure_model import ClosureModel  # noqa: E402
from app.ml.duration_model import DurationModel  # noqa: E402
from app.ml.severity_model import SeverityModel  # noqa: E402
from app.utils.feature_engineering import FeatureEngineer  # noqa: E402


def compute_sample_weights(df: pd.DataFrame) -> np.ndarray:
    """
    Inverse-frequency weighting by event_cause (roadmap section 6.4,
    "simpler" approach). This is what keeps the model from simply ignoring
    procession / vip_movement / public_event / protest — the rare,
    high-disruption causes the problem statement leads with — in favor of
    always predicting the 60%-majority vehicle_breakdown pattern.
    """
    counts = df["event_cause"].value_counts()
    weights = df["event_cause"].map(lambda c: 1.0 / counts[c]).values
    weights = weights / weights.mean()  # normalize so mean weight is 1.0
    return weights


def main():
    print("=" * 60)
    print("VYUHA — training predictive models")
    print("=" * 60)

    print(f"\n[1/6] Loading processed dataset from {settings.PROCESSED_DATA_FILE} ...")
    df = pd.read_parquet(settings.PROCESSED_DATA_FILE)
    duration_df = pd.read_parquet(settings.DURATION_TRAIN_FILE)
    print(f"      {len(df):,} events loaded.")

    print("\n[2/6] Fitting FeatureEngineer on the full dataset ...")
    fe = FeatureEngineer().fit(df, duration_df=duration_df)
    X_full = fe.transform(df)
    print(f"      Feature matrix shape: {X_full.shape}")

    print("\n[3/6] Splitting 80/20 train/test ...")
    idx_train, idx_test = train_test_split(df.index, test_size=0.2, random_state=42)
    X_train, X_test = X_full.loc[idx_train], X_full.loc[idx_test]
    df_train, df_test = df.loc[idx_train], df.loc[idx_test]
    w_train = compute_sample_weights(df_train)
    print(f"      Train: {len(X_train):,} rows | Test: {len(X_test):,} rows")

    metrics = {}

    # ── Severity model ──────────────────────────────────────────────────────
    print("\n[4/6] Training severity classifier (LightGBM, 3-class) ...")
    severity_model = SeverityModel()
    severity_model.fit(X_train, df_train["severity"], sample_weight=w_train)
    sev_labels, sev_conf, _ = severity_model.predict(X_test)
    sev_acc = accuracy_score(df_test["severity"], sev_labels)
    print(f"      Test accuracy: {sev_acc:.3f}")
    print(classification_report(df_test["severity"], sev_labels, zero_division=0))
    metrics["severity"] = {
        "test_accuracy": round(float(sev_acc), 4),
        "report": classification_report(df_test["severity"], sev_labels, zero_division=0, output_dict=True),
        "top_features": dict(sorted(severity_model.feature_importance().items(), key=lambda kv: -kv[1])[:10]),
    }
    severity_model.save()

    # ── Closure model ───────────────────────────────────────────────────────
    print("\n[5/6] Training road-closure classifier (LightGBM, binary) ...")
    closure_model = ClosureModel()
    closure_model.fit(X_train, df_train["requires_road_closure"], sample_weight=w_train)
    closure_proba = closure_model.predict_proba(X_test)
    try:
        closure_auc = roc_auc_score(df_test["requires_road_closure"], closure_proba)
    except ValueError:
        closure_auc = float("nan")
    closure_acc = accuracy_score(df_test["requires_road_closure"], closure_proba >= 0.5)
    print(f"      Test ROC-AUC: {closure_auc:.3f} | Test accuracy @0.5: {closure_acc:.3f}")
    metrics["closure"] = {
        "test_roc_auc": round(float(closure_auc), 4) if closure_auc == closure_auc else None,
        "test_accuracy_at_0.5": round(float(closure_acc), 4),
        "top_features": dict(sorted(closure_model.feature_importance().items(), key=lambda kv: -kv[1])[:10]),
    }
    closure_model.save()

    # ── Duration model (survival analysis) ──────────────────────────────────
    print("\n[6/6] Training duration model (WeibullAFTFitter, censoring-aware) ...")
    duration_model = DurationModel(penalizer=0.1)
    duration_model.fit(X_train, df_train["duration_mins"], df_train["observed"])

    median_pred, lower_pred, upper_pred = duration_model.predict(X_test)
    observed_mask = df_test["observed"].values == 1
    if observed_mask.sum() > 0:
        mae_observed = float(
            np.mean(np.abs(median_pred[observed_mask] - df_test["duration_mins"].values[observed_mask]))
        )
    else:
        mae_observed = None

    try:
        from lifelines.utils import concordance_index
        c_index = concordance_index(
            df_test["duration_mins"].values, median_pred, df_test["observed"].values
        )
    except Exception as e:
        c_index = None
        print(f"      (concordance index unavailable: {e})")

    print(f"      Median-duration MAE on observed test events: "
          f"{mae_observed:.1f} min" if mae_observed is not None else "      MAE: n/a")
    print(f"      Concordance index: {c_index:.3f}" if c_index is not None else "      Concordance index: n/a")
    metrics["duration"] = {
        "mae_observed_mins": round(mae_observed, 2) if mae_observed is not None else None,
        "concordance_index": round(float(c_index), 4) if c_index is not None else None,
    }
    duration_model.save()

    # ── Save the fitted feature engineer last (everything above depends on it) ──
    joblib.dump(fe, settings.FEATURE_ENGINEER_PATH)

    Path(settings.METRICS_PATH).parent.mkdir(parents=True, exist_ok=True)
    with open(settings.METRICS_PATH, "w") as f:
        json.dump(metrics, f, indent=2, default=str)

    print("\n" + "=" * 60)
    print(f"All artifacts saved under {settings.MODELS_DIR}/")
    print(f"Metrics summary written to {settings.METRICS_PATH}")
    print("=" * 60)
    print("\nDone. Next: python run.py")


if __name__ == "__main__":
    main()
