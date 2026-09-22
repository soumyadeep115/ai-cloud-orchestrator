"""
Breaks down live (backfilled) prediction accuracy by which traffic
phase was active at the time, instead of one pooled number that hides
very different regimes (idle vs. periodic vs. spike) inside a single
average.

The predictions table has no "which k6 profile was running" label, so
the time windows below are read off your own terminal timestamps from
today's two predict_poller.py runs. EDIT THE WINDOWS BELOW if your
actual run times differ, or if you gather more rounds later and want
to add windows for them.

All window times are IST (UTC+5:30), matching what your terminal
printed, and are converted to UTC internally to match the ts column.

Requires: pip install pytz --break-system-packages  (or use zoneinfo,
Python 3.9+, no install needed — this script uses zoneinfo)

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

# (label, start HH:MM:SS IST, end HH:MM:SS IST) — today's date assumed.
# Based on your predict_poller.py terminal output:
WINDOWS = [
    ("idle (low VU, easy)",              "20:33:00", "20:35:30"),
    ("idle->periodic contention gap",    "20:35:30", "20:40:00"),
    ("periodic ramp (moderate transition)", "20:40:00", "20:48:20"),
    ("spike run (pre-contention)",       "20:53:00", "20:57:00"),
    ("spike peak contention",            "20:57:00", "20:59:00"),
]


def window_to_utc(date_today, hms_start, hms_end):
    start = datetime.strptime(f"{date_today} {hms_start}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST)
    end = datetime.strptime(f"{date_today} {hms_end}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST)
    return start.astimezone(ZoneInfo("UTC")), end.astimezone(ZoneInfo("UTC"))


def main():
    db = SessionLocal()

    all_preds = db.scalars(
        select(Prediction).where(Prediction.actual_request_rate.is_not(None))
    ).all()

    print(f"Total backfilled predictions available: {len(all_preds)}\n")

    today = datetime.now(IST).strftime("%Y-%m-%d")
    labeled_count = 0

    for label, start_hms, end_hms in WINDOWS:
        win_start, win_end = window_to_utc(today, start_hms, end_hms)
        bucket = [p for p in all_preds if win_start <= p.ts < win_end]

        if not bucket:
            print(f"--- {label} ---")
            print(f"  No predictions in this window ({start_hms}-{end_hms} IST)\n")
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