"""
Background decision loop (dry-run: logs decisions, does not scale k8s).

Place at: backend/app/orchestration/loop.py
Run (separate terminal, next to `python -m app.poller`):
    cd backend && python -m app.orchestration.loop

Env: DECISION_CLUSTERS (comma-separated names, default "cluster-b")
     DECISION_INTERVAL_SECONDS (default 15)
A cluster is only re-evaluated when a NEW metrics row has arrived since the
last decision, so a slow poller doesn't produce duplicate decisions.
"""

import os
import time
import traceback

from sqlalchemy import func, select

from ..database import SessionLocal
from ..models import Cluster, Metric
from .decision import decide_scaling_action

CLUSTER_NAMES = [c.strip() for c in os.getenv("DECISION_CLUSTERS", "cluster-b").split(",") if c.strip()]
INTERVAL_SECONDS = int(os.getenv("DECISION_INTERVAL_SECONDS", "15"))


def main():
    last_seen = {}
    print(f"decision loop: clusters={CLUSTER_NAMES} interval={INTERVAL_SECONDS}s (dry-run)")
    while True:
        for name in CLUSTER_NAMES:
            try:
                with SessionLocal() as db:
                    cid = db.scalar(select(Cluster.id).where(Cluster.name == name))
                    latest = db.scalar(select(func.max(Metric.ts)).where(Metric.cluster_id == cid)) if cid else None
                if cid is None or latest is None or latest == last_seen.get(cid):
                    continue
                d = decide_scaling_action(cid, commit=True)
                last_seen[cid] = latest
                print(f"[{d.ts:%H:%M:%S}] {name}: {d.action} {d.prev_replicas}->{d.next_replicas} "
                      f"({d.source}, {d.regime}, conf {d.confidence})")
            except Exception:
                traceback.print_exc()
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()