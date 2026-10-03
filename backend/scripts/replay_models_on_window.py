"""
Replays both the OLD (pre-more-spike-data) and NEW (post-more-spike-data)
models against the exact same historical feature rows from a given live
window — isolating whether a model change caused a live MAE regression,
or whether a harder/different traffic instance did.

For each backfilled prediction in the window, reconstructs the feature
row from the metrics table exactly as predictor.py would have at that
moment (same rows, same lag/rolling logic), then scores it with both
model files. The NEW model's replayed prediction should closely match
what predict_poller.py actually recorded live — that match is a
correctness check on the replay logic itself before trusting the OLD
model's counterfactual numbers.

Place at: backend/scripts/replay_models_on_window.py
Usage:
    python replay_models_on_window.py
"""

from datetime import datetime
from zoneinfo import ZoneInfo
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
import numpy as np
import pandas as pd
import xgboost as xgb

from app.database import SessionLocal
from app.models import Prediction, Metric

IST = ZoneInfo("Asia/Kolkata")

# Edit this to whichever window you want to replay.
WINDOW_LABEL = "spike after more data (2 bursts)"
WINDOW_START = "2026-10-03 20:43:08"
WINDOW_END = "2026-10-03 20:49:18"

# Must match predictor.py exactly.
LAGS = [1, 2, 3]
ROLLING_WINDOW = 5
VALUE_COLS = ["cpu_percent", "memory_percent", "request_rate", "latency_ms"]
MIN_ROWS_NEEDED = max(LAGS) + ROLLING_WINDOW - 1
FETCH_ROWS = MIN_ROWS_NEEDED + 3

ML_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "ml")
OLD_MODEL_PATH = os.path.join(ML_DIR, "production_model_backup_pre_more_spike_data.json")
NEW_MODEL_PATH = os.path.join(ML_DIR, "production_model.json")


def _feature_columns():
    cols = []
    for col in VALUE_COLS:
        for lag in LAGS:
            cols.append(f"{col}_lag{lag}")
        cols.append(f"{col}_roll_mean")
        cols.append(f"{col}_roll_std")
    return cols


FEATURE_COLUMNS = _feature_columns()


def build_feature_row(rows_chronological):
    if len(rows_chronological) < MIN_ROWS_NEEDED:
        return None

    df = pd.DataFrame(rows_chronological)

    for col in VALUE_COLS:
        for lag in LAGS:
            df[f"{col}_lag{lag}"] = df[col].shift(lag)
        df[f"{col}_roll_mean"] = df[col].rolling(ROLLING_WINDOW).mean()
        df[f"{col}_roll_std"] = df[col].rolling(ROLLING_WINDOW).std()

    latest = df.iloc[[-1]][FEATURE_COLUMNS]

    if latest.isnull().any(axis=1).iloc[0]:
        return None

    return latest


def window_to_utc(dt_str_start, dt_str_end):
    start = datetime.strptime(dt_str_start, "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST)
    end = datetime.strptime(dt_str_end, "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST)
    return start.astimezone(ZoneInfo("UTC")), end.astimezone(ZoneInfo("UTC"))


def main():
    if not os.path.exists(OLD_MODEL_PATH):
        print(f"FAIL: old model backup not found at {OLD_MODEL_PATH}")
        print("Check the exact filename you backed up to and update OLD_MODEL_PATH.")
        return

    old_model = xgb.XGBRegressor()
    old_model.load_model(OLD_MODEL_PATH)

    new_model = xgb.XGBRegressor()
    new_model.load_model(NEW_MODEL_PATH)

    db = SessionLocal()

    win_start, win_end = window_to_utc(WINDOW_START, WINDOW_END)

    preds = db.scalars(
        select(Prediction)
        .where(Prediction.actual_request_rate.is_not(None))
        .where(Prediction.ts >= win_start)
        .where(Prediction.ts < win_end)
        .order_by(Prediction.ts.asc())
    ).all()

    if not preds:
        print(f"No backfilled predictions found in window {WINDOW_START} - {WINDOW_END} IST.")
        return

    print(f"--- {WINDOW_LABEL} (n={len(preds)}) ---\n")
    print(f"{'ts (IST)':<10} {'actual':>8} {'live(new)':>10} {'replay(new)':>12} {'replay(old)':>12}")

    old_errors, new_errors, replay_match_diffs = [], [], []
    skipped = 0

    for p in preds:
        rows = db.scalars(
            select(Metric)
            .where(Metric.cluster_id == p.cluster_id)
            .where(Metric.ts <= p.ts)
            .order_by(Metric.ts.desc())
            .limit(FETCH_ROWS)
        ).all()

        rows_chronological = [
            {
                "cpu_percent": r.cpu_percent,
                "memory_percent": r.memory_percent,
                "request_rate": r.request_rate,
                "latency_ms": r.latency_ms,
            }
            for r in reversed(rows)
        ]

        features = build_feature_row(rows_chronological)
        if features is None:
            skipped += 1
            continue

        old_pred = max(0.0, float(old_model.predict(features)[0]))
        new_pred = max(0.0, float(new_model.predict(features)[0]))

        old_err = abs(old_pred - p.actual_request_rate)
        new_err = abs(new_pred - p.actual_request_rate)
        old_errors.append(old_err)
        new_errors.append(new_err)
        replay_match_diffs.append(abs(new_pred - p.predicted_request_rate))

        ts_ist = p.ts.astimezone(IST).strftime("%H:%M:%S")
        print(f"{ts_ist:<10} {p.actual_request_rate:>8.3f} {p.predicted_request_rate:>10.3f} "
              f"{new_pred:>12.3f} {old_pred:>12.3f}")

    print()
    if skipped:
        print(f"Skipped {skipped} prediction(s) — insufficient/NULL metric history to rebuild features.\n")

    if not old_errors:
        print("No predictions could be replayed.")
        return

    avg_replay_diff = float(np.mean(replay_match_diffs))
    print(f"Replay sanity check: new-model replay vs. actual live prediction, avg diff = {avg_replay_diff:.4f}")
    if avg_replay_diff > 0.05:
        print("  WARNING: this should be ~0 — replay logic may not exactly match predictor.py. "
              "Treat the old-vs-new comparison below with caution until this is resolved.\n")
    else:
        print("  Matches closely — replay logic is faithful, old-model numbers below are trustworthy.\n")

    old_mae = float(np.mean(old_errors))
    new_mae = float(np.mean(new_errors))
    print(f"OLD model MAE (counterfactual, same inputs): {old_mae:.3f}")
    print(f"NEW model MAE (same inputs, matches live):   {new_mae:.3f}")

    if new_mae < old_mae:
        print(f"\nNEW model is genuinely better on this exact data ({((old_mae-new_mae)/old_mae*100):.1f}% improvement) "
              f"— today's traffic instance was likely just harder for naive too, not a model regression.")
    else:
        print(f"\nOLD model would have done better on this exact data ({((new_mae-old_mae)/old_mae*100):.1f}% worse) "
              f"— this points to a real regression from the extra spike training data (possible overfitting "
              f"to the repeated k6 spike profile shape), not traffic-instance noise.")

    db.close()


if __name__ == "__main__":
    main()