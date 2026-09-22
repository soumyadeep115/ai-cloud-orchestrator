import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db, SessionLocal
from ..models import Cluster, Metric
from ..prometheus import cluster_metrics

router = APIRouter(prefix="/clusters", tags=["clusters"])


@router.get("")
async def get_clusters():
    # Open the DB session ONLY for the quick SELECT, and pull the plain
    # values out of the ORM objects before closing it. This is the fix:
    # previously the session (via Depends) stayed open for the entire
    # function, including the slow Prometheus loop below — under
    # concurrent polling that held connections open for up to a minute
    # each and exhausted the pool. Now the session closes immediately
    # after this block, well before any network I/O to Prometheus.
    with SessionLocal() as db:
        clusters = db.scalars(select(Cluster).order_by(Cluster.id)).all()
        cluster_data = [(c.id, c.name) for c in clusters]

    # Run all clusters' Prometheus lookups concurrently instead of one
    # at a time — this also directly shrinks the worst-case request
    # time (previously up to ~60s sequential, now capped at whatever
    # the single slowest cluster takes), which further reduces the
    # chance of polls piling up in the first place.
    live_results = await asyncio.gather(
        *(cluster_metrics(name) for _, name in cluster_data)
    )

    response = []
    for (cluster_id, name), live in zip(cluster_data, live_results):
        reachable = any(value is not None for value in live.values())
        response.append(
            {
                "id": cluster_id,
                "name": name,
                "status": "healthy" if reachable else "unreachable",
                "cpu_percent": live["cpu_percent"],
                "memory_percent": live["memory_percent"],
                "pod_count": live["pod_count"],
                "node_count": live["node_count"],
                "request_rate": live["request_rate"],
                "latency_ms": live["p99_latency_ms"],
            }
        )

    return response


@router.get("/{cluster_id}/metrics")
async def get_cluster_metrics(
    cluster_id: int,
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    # This route is fine as-is: it ONLY touches the database, no slow
    # external I/O happens while the session is open, so there's no
    # equivalent pool-exhaustion risk here.
    cluster = db.get(Cluster, cluster_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    rows = db.scalars(
        select(Metric)
        .where(Metric.cluster_id == cluster_id)
        .order_by(Metric.ts.desc())
        .limit(limit)
    ).all()

    return {
        "cluster_id": cluster.id,
        "cluster_name": cluster.name,
        "metrics": [
            {
                "timestamp": row.ts,
                "cpu_percent": row.cpu_percent,
                "memory_percent": row.memory_percent,
                "request_rate": row.request_rate,
                "latency_ms": row.latency_ms,
                "pod_count": row.pod_count,
                "node_count": row.node_count,
            }
            for row in reversed(rows)
        ],
    }
