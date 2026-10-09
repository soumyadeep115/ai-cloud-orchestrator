"""
Background decision loop. Dry-run by default; live scaling with ACTUATE=true.

Place at: backend/app/orchestration/loop.py   (replaces the old file)
Run (separate terminal, next to `python -m app.poller`):
    cd backend && python -m app.orchestration.loop

Env: DECISION_CLUSTERS (comma-separated names, default "cluster-b")
     DECISION_INTERVAL_SECONDS (default 15)
     ACTUATE (default false). true -> really scale the k8s deployment.
A cluster is only re-evaluated when a NEW metrics row has arrived since the
last decision, so a slow poller doesn't produce duplicate decisions.
"""

import os
import sys
import time
import traceback

from sqlalchemy import func, select

from ..database import SessionLocal
from ..models import Cluster, Metric
from .decision import DECISION_MODE, decide_scaling_action

CLUSTER_NAMES = [c.strip() for c in os.getenv("DECISION_CLUSTERS", "cluster-b").split(",") if c.strip()]
INTERVAL_SECONDS = int(os.getenv("DECISION_INTERVAL_SECONDS", "15"))
ACTUATE = os.getenv("ACTUATE", "false").strip().lower() in ("1", "true", "yes")

if ACTUATE:
    from . import actuator
    from .actuator import ActuationError


def _check_cluster_access():
    """Fail fast at startup if live mode can't reach the deployment."""
    for name in CLUSTER_NAMES:
        try:
            st = actuator.get_status(name)
            print(f"  {name}: {actuator.NAMESPACE}/{actuator.DEPLOYMENT} "
                  f"desired={st.desired} ready={st.ready}")
        except ActuationError as exc:
            print(f"STARTUP CHECK FAILED: {exc}")
            sys.exit(1)


def main():
    last_seen = {}
    mode = "LIVE - will scale the deployment" if ACTUATE else "dry-run"
    print(f"decision loop: clusters={CLUSTER_NAMES} interval={INTERVAL_SECONDS}s ({mode}) decision-mode={DECISION_MODE}")
    if ACTUATE:
        print(f"  live replica range: {actuator.clamp_live(0)}..{actuator.LIVE_MAX_REPLICAS}")
        _check_cluster_access()

    while True:
        for name in CLUSTER_NAMES:
            try:
                with SessionLocal() as db:
                    cid = db.scalar(select(Cluster.id).where(Cluster.name == name))
                    latest = db.scalar(select(func.max(Metric.ts)).where(Metric.cluster_id == cid)) if cid else None
                if cid is None or latest is None or latest == last_seen.get(cid):
                    continue

                # Live mode: the cluster is the source of truth for the current
                # replica count. If we can't read it, don't decide blind.
                actual = None
                if ACTUATE:
                    try:
                        actual = actuator.get_replicas(name)
                    except ActuationError as exc:
                        print(f"[{time.strftime('%H:%M:%S')}] {name}: SKIPPED cycle - {exc}")
                        continue

                d = decide_scaling_action(cid, commit=True, current_replicas=actual)
                last_seen[cid] = latest
                line = (f"[{d.ts:%H:%M:%S}] {name}: {d.action} {d.prev_replicas}->{d.next_replicas} "
                        f"({d.source}, {d.regime}, conf {d.confidence})")

                if ACTUATE:
                    target = actuator.clamp_live(d.next_replicas)
                    if target != actual:
                        try:
                            applied = actuator.set_replicas(name, target)
                            line += f" | APPLIED k8s {actual}->{applied}"
                            if applied != d.next_replicas:
                                line += f" (live cap, decision wanted {d.next_replicas})"
                        except ActuationError as exc:
                            line += f" | APPLY FAILED: {exc}"
                    else:
                        line += f" | k8s already at {actual}"
                print(line)
            except Exception:
                traceback.print_exc()
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()