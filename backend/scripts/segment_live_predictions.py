"""
Breaks down live (backfilled) prediction accuracy by which traffic
phase was active at the time, instead of one pooled number that hides
very different regimes (idle vs. periodic vs. spike) inside a single
average.

The predictions table has no "which k6 profile was running" label, so
the time windows below are read off your own terminal timestamps.
EDIT THE WINDOWS BELOW if your actual run times differ, or if you
gather more rounds later and want to add windows for them.

All window times are IST (UTC+5:30), matching what your terminal
printed, and are converted to UTC internally to match the ts column.

Usage:
    python segment_live_predictions.py
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
import numpy as np

from app.database import SessionLocal
from app.models import Prediction

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
]


def window_to_utc(dt_str_start, dt_str_end):
    start = datetime.strptime(dt_str_start, "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST)
    end = datetime.strptime(dt_str_end, "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST)
    return start.astimezone(ZoneInfo("UTC")), end.astimezone(ZoneInfo("UTC"))


def main():
    db = SessionLocal()

    all_preds = db.scalars(
        select(Prediction).where(Prediction.actual_request_rate.is_not(None))
    ).all()

    print(f"Total backfilled predictions available: {len(all_preds)}\n")

    labeled_count = 0

    for label, start_dt, end_dt in WINDOWS:
        win_start, win_end = window_to_utc(start_dt, end_dt)
        bucket = [p for p in all_preds if win_start <= p.ts < win_end]

        if not bucket:
            print(f"--- {label} ---")
            print(f"  No predictions in this window ({start_dt} to {end_dt} IST)\n")
            continue

        errors = [abs(p.predicted_request_rate - p.actual_request_rate) for p in bucket]
        mae = float(np.mean(errors))
        rmse = float(np.sqrt(np.mean(np.square(errors))))
        labeled_count += len(bucket)

        print(f"--- {label} (n={len(bucket)}) ---")
        print(f"  MAE:  {mae:.3f}")
        print(f"  RMSE: {rmse:.3f}\n")

    unlabeled = len(all_preds) - labeled_count
    if unlabeled > 0:
        print(f"Note: {unlabeled} backfilled prediction(s) fell outside all defined windows "
              f"(adjust WINDOWS at the top of this script if you've run more rounds).")

    db.close()


if __name__ == "__main__":
    main()