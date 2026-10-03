"""
Confirms the newly copied production_model.json loads correctly and
produces a sane prediction, using the exact same code path as the real
/clusters/{id}/predict endpoint — NOT a mock. Run this right after
copying a new model into backend/app/ml/production_model.json, before
trusting it in a live poller session.

Place at: backend/scripts/sanity_check_deploy.py
Usage:
    python sanity_check_deploy.py <cluster_id>
    (defaults to cluster_id=1 if omitted — check your clusters table
    if unsure which id is cluster-b)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Cluster, Metric
from app.ml.predictor import predict_request_rate, InsufficientDataError, FETCH_ROWS, HORIZON_SECONDS


def main():
    cluster_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1

    db = SessionLocal()

    cluster = db.get(Cluster, cluster_id)
    if not cluster:
        print(f"FAIL: no cluster with id={cluster_id}. Check your clusters table for the right id.")
        return

    rows = db.scalars(
        select(Metric)
        .where(Metric.cluster_id == cluster_id)
        .order_by(Metric.ts.desc())
        .limit(FETCH_ROWS)
    ).all()

    if not rows:
        print(f"FAIL: no metrics rows found for cluster_id={cluster_id} ({cluster.name}).")
        return

    rows_chronological = [
        {
            "cpu_percent": r.cpu_percent,
            "memory_percent": r.memory_percent,
            "request_rate": r.request_rate,
            "latency_ms": r.latency_ms,
        }
        for r in reversed(rows)
    ]

    print(f"Cluster: {cluster.name} (id={cluster_id})")
    print(f"Fetched {len(rows_chronological)} recent rows (need >= {FETCH_ROWS - 3})")
    print(f"Most recent request_rate on record: {rows_chronological[-1]['request_rate']}")

    try:
        predicted = predict_request_rate(rows_chronological)
    except InsufficientDataError as e:
        print(f"FAIL: {e}")
        return

    print(f"\nPredicted request_rate (~{HORIZON_SECONDS}s ahead): {predicted:.3f}")

    last_actual = rows_chronological[-1]["request_rate"]
    if last_actual is not None:
        diff_pct = abs(predicted - last_actual) / max(last_actual, 0.01) * 100
        print(f"Diff vs most recent actual ({last_actual:.3f}): {diff_pct:.1f}%")
        if diff_pct > 500:
            print("WARNING: prediction is wildly far from the last known value — "
                  "possible feature/scale mismatch. Don't trust this model yet.")
        else:
            print("Looks sane. Safe to proceed to a live poller session.")

    db.close()


if __name__ == "__main__":
    main()