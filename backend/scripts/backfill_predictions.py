"""
Backfills predictions.actual_request_rate for any prediction whose
horizon has now passed, by looking up the real request_rate that was
actually observed at (prediction.ts + horizon_seconds).

This turns the predictions table from a one-off log into a running
accuracy record: once backfilled, you can compute real MAE/RMSE across
every live prediction the /predict endpoint has ever made, not just
the single point-in-time check done during development.

Place at: backend/scripts/backfill_predictions.py
Run manually, or on a schedule (cron / Windows Task Scheduler) every
few minutes so predictions get backfilled soon after their horizon
passes rather than accumulating unbackfilled for a long time.

Usage:
    python backfill_predictions.py
"""

from datetime import timedelta
import os
import sys

# Make sure `backend/` (the parent of this scripts/ folder) is on the
# import path, so `from app.database import ...` resolves no matter
# how this script is invoked (python scripts\backfill_predictions.py,
# double-click, a scheduled task, etc.) rather than only working when
# run as `python -m scripts.backfill_predictions`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, and_
import numpy as np

from app.database import SessionLocal
from app.models import Prediction, Metric

# How far off the target timestamp a metrics row is allowed to be and
# still count as "the observed value at that time" — the poller's
# 15s interval means the nearest real sample is usually within ~7.5s;
# 30s gives headroom for a missed/delayed poll cycle.
MATCH_TOLERANCE_SECONDS = 30


def find_nearest_metric(db, cluster_id, target_ts):
    """Returns the metrics row for this cluster whose ts is closest to
    target_ts, restricted to a window around it, or None if nothing
    is close enough to trust as "the observed value at that time"."""
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

    # Pick whichever candidate is closest in time to the exact target
    return min(rows, key=lambda r: abs((r.ts - target_ts).total_seconds()))


def main():
    db = SessionLocal()

    pending = db.scalars(
        select(Prediction).where(Prediction.actual_request_rate.is_(None))
    ).all()

    print(f"Found {len(pending)} prediction(s) awaiting backfill.")

    backfilled = 0
    still_too_early = 0
    no_match_found = 0

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    for pred in pending:
        target_ts = pred.ts + timedelta(seconds=pred.horizon_seconds)

        if target_ts > now:
            # Horizon hasn't actually passed yet — nothing to backfill.
            still_too_early += 1
            continue

        match = find_nearest_metric(db, pred.cluster_id, target_ts)

        if match is None:
            # No real observation close enough to target_ts to trust
            # (e.g. poller was down, or cluster was briefly unreachable).
            no_match_found += 1
            continue

        pred.actual_request_rate = match.request_rate
        backfilled += 1

    db.commit()

    print(f"Backfilled:        {backfilled}")
    print(f"Still too early:   {still_too_early} (horizon hasn't passed yet)")
    print(f"No match found:    {no_match_found} (no metrics row close enough to target time)")

    # Running accuracy across everything backfilled so far, not just
    # this run — gives a real, accumulating accuracy record.
    all_backfilled = db.scalars(
        select(Prediction).where(Prediction.actual_request_rate.is_not(None))
    ).all()

    if all_backfilled:
        errors = [
            abs(p.predicted_request_rate - p.actual_request_rate)
            for p in all_backfilled
            if p.predicted_request_rate is not None
        ]
        if errors:
            mae = float(np.mean(errors))
            rmse = float(np.sqrt(np.mean(np.square(errors))))
            print(f"\nRunning accuracy across {len(errors)} backfilled prediction(s):")
            print(f"  MAE:  {mae:.3f}")
            print(f"  RMSE: {rmse:.3f}")
    else:
        print("\nNo backfilled predictions yet to compute accuracy from.")

    db.close()


if __name__ == "__main__":
    main()