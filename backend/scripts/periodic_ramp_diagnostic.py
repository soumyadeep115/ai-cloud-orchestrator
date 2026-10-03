"""
Prints predicted vs. actual, in time order, for the periodic-ramp
window only — to see WHY the model loses to naive there before
deciding whether to weight it, re-feature it, or leave it to naive.

Two failure modes look different here:
  - Model consistently trails the rising/falling trend (predictions
    lag behind actual by roughly one step) -> a lag/smoothing problem,
    fixable with rate-of-change features.
  - Model errors look unrelated to the ramp's direction/shape ->
    weighting or extra features won't help; naive is just genuinely
    hard to beat here and it should be left alone.

Place at: backend/scripts/periodic_ramp_diagnostic.py
Usage:
    python periodic_ramp_diagnostic.py
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Prediction

IST = ZoneInfo("Asia/Kolkata")

# Copy this exactly from segment_live_predictions.py / naive_vs_model_spike.py
RUN_DATE = "2026-09-19"
WINDOW_LABEL = "periodic ramp (moderate transition)"
WINDOW_START = "20:40:00"
WINDOW_END = "20:48:20"


def window_to_utc(date_str, hms_start, hms_end):
    start = datetime.strptime(f"{date_str} {hms_start}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST)
    end = datetime.strptime(f"{date_str} {hms_end}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST)
    return start.astimezone(ZoneInfo("UTC")), end.astimezone(ZoneInfo("UTC"))


def main():
    db = SessionLocal()

    win_start, win_end = window_to_utc(RUN_DATE, WINDOW_START, WINDOW_END)

    bucket = db.scalars(
        select(Prediction)
        .where(Prediction.actual_request_rate.is_not(None))
        .where(Prediction.ts >= win_start)
        .where(Prediction.ts < win_end)
        .order_by(Prediction.ts.asc())
    ).all()

    if not bucket:
        print(f"No predictions found in '{WINDOW_LABEL}' window — check RUN_DATE/WINDOW_START/END.")
        return

    print(f"--- {WINDOW_LABEL} (n={len(bucket)}) ---\n")
    print(f"{'ts (IST)':<20} {'predicted':>10} {'actual':>10} {'error':>10} {'direction':>12}")

    prev_actual = None
    lag_like_count = 0
    scattered_count = 0

    for p in bucket:
        ts_ist = p.ts.astimezone(IST).strftime("%H:%M:%S")
        error = p.predicted_request_rate - p.actual_request_rate

        direction = ""
        if prev_actual is not None:
            actual_rising = p.actual_request_rate > prev_actual
            # If actual is rising and the model under-predicted (trailing
            # behind the rise), or actual is falling and model over-
            # predicted (trailing behind the fall), that's the lag pattern.
            if (actual_rising and error < 0) or (not actual_rising and error > 0):
                direction = "trailing"
                lag_like_count += 1
            else:
                direction = "not-trailing"
                scattered_count += 1

        print(f"{ts_ist:<20} {p.predicted_request_rate:>10.3f} {p.actual_request_rate:>10.3f} {error:>10.3f} {direction:>12}")
        prev_actual = p.actual_request_rate

    print(f"\nTrailing the trend: {lag_like_count} / {lag_like_count + scattered_count} predictions")
    if lag_like_count + scattered_count > 0:
        pct = lag_like_count / (lag_like_count + scattered_count) * 100
        if pct >= 65:
            print(f"({pct:.0f}%) -> looks like a LAG problem. Rate-of-change features are likely to help.")
        elif pct <= 35:
            print(f"({pct:.0f}%) -> errors don't track the trend direction -> looks SCATTERED, "
                  f"not a lag problem. Weighting/new features may not help; naive may just be better here.")
        else:
            print(f"({pct:.0f}%) -> mixed, not a clean signal either way. Worth a bigger sample before deciding.")

    db.close()


if __name__ == "__main__":
    main()