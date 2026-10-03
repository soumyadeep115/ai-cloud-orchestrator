"""
Naive-vs-model live comparison, specifically for the spike window.

Reuses the same WINDOWS-based time-bucketing approach as
segment_live_predictions.py, but for each backfilled prediction in the
spike window(s) it also looks up what the naive baseline (last observed
request_rate at prediction time) would have predicted, then compares
naive's error against the model's error on the exact same predictions.

This closes the open item from the live-validation report: the model's
own spike-window error was measured, but naive's live error in that same
window never was.

Place at: backend/scripts/naive_vs_model_spike.py

Usage:
    python naive_vs_model_spike.py
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, and_
import numpy as np

from app.database import SessionLocal
from app.models import Prediction, Metric

IST = ZoneInfo("Asia/Kolkata")

# Full datetime literals (date+time together) so a session that crosses
# midnight — like this one, 23:53 -> 01:59 — can't silently produce a
# broken (end < start) window.
WINDOWS = [
    ("idle #1",            "2026-09-26 23:53:36", "2026-09-27 00:12:37"),
    ("long_ramp",          "2026-09-27 00:14:37", "2026-09-27 00:43:39"),
    ("sustained",          "2026-09-27 00:45:39", "2026-09-27 01:08:42"),
    ("periodic",           "2026-09-27 01:10:42", "2026-09-27 01:30:44"),
    ("spike (full run)",   "2026-09-27 01:32:44", "2026-09-27 01:34:26"),
    ("spike peak (20 VU)", "2026-09-27 01:33:24", "2026-09-27 01:33:54"),
    ("ramp",               "2026-09-27 01:36:26", "2026-09-27 01:38:27"),
    ("idle #2",            "2026-09-27 01:40:27", "2026-09-27 01:59:28"),
    ("spike isolated (2x back-to-back)", "2026-09-27 02:24:21", "2026-09-27 02:29:46"),
    ("spike after more data (2 bursts)", "2026-10-03 20:43:08", "2026-10-03 20:49:18"),
]

# Same tolerance as backfill_predictions.py, applied here to find the
# naive "prediction" — the request_rate observed AT prediction time
# (pred.ts), not at the future target_ts. This is exactly what
# compute_naive_baseline() in train_model.py uses: predicted = last
# known value when the prediction was made.
MATCH_TOLERANCE_SECONDS = 30


def window_to_utc(dt_str_start, dt_str_end):
    start = datetime.strptime(dt_str_start, "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST)
    end = datetime.strptime(dt_str_end, "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST)
    return start.astimezone(ZoneInfo("UTC")), end.astimezone(ZoneInfo("UTC"))


def find_nearest_metric_at(db, cluster_id, target_ts):
    window_start = target_ts - timedelta(seconds=MATCH_TOLERANCE_SECONDS)
    window_end = target_ts + timedelta(seconds=MATCH_TOLERANCE_SECONDS)

    rows = db.scalars(
        select(Metric).where(
            and_(
                Metric.cluster_id == cluster_id,
                Metric.ts >= window_start,
                Metric.ts <= window_end,
                Metric.request_rate.is_not(None),
            )
        )
    ).all()

    if not rows:
        return None
    return min(rows, key=lambda r: abs((r.ts - target_ts).total_seconds()))


def main():
    db = SessionLocal()

    all_preds = db.scalars(
        select(Prediction).where(Prediction.actual_request_rate.is_not(None))
    ).all()

    for label, start_dt, end_dt in WINDOWS:
        win_start, win_end = window_to_utc(start_dt, end_dt)
        bucket = [p for p in all_preds if win_start <= p.ts < win_end]

        if not bucket:
            print(f"--- {label} ---")
            print(f"  No predictions in this window ({start_dt} to {end_dt} IST)\n")
            continue

        model_errors = []
        naive_errors = []
        skipped_no_naive_match = 0

        for p in bucket:
            model_errors.append(abs(p.predicted_request_rate - p.actual_request_rate))

            naive_metric = find_nearest_metric_at(db, p.cluster_id, p.ts)
            if naive_metric is None:
                skipped_no_naive_match += 1
                continue
            naive_errors.append(abs(naive_metric.request_rate - p.actual_request_rate))

        model_mae = float(np.mean(model_errors))
        print(f"--- {label} (n={len(bucket)}) ---")
        print(f"  Model MAE: {model_mae:.3f}")

        if naive_errors:
            naive_mae = float(np.mean(naive_errors))
            verdict = "MODEL BEATS naive" if model_mae < naive_mae else "naive BEATS model"
            delta_pct = ((model_mae - naive_mae) / naive_mae) * 100
            print(f"  Naive MAE: {naive_mae:.3f}  (n={len(naive_errors)})")
            print(f"  {verdict} live in this window ({delta_pct:+.1f}% vs naive)")
        else:
            print("  Naive MAE: could not compute (no matching metric found at prediction time)")

        if skipped_no_naive_match:
            print(f"  Note: {skipped_no_naive_match} prediction(s) skipped for naive (no metric row close enough to pred.ts)")
        print()

    db.close()


if __name__ == "__main__":
    main()