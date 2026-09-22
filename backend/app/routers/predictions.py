"""
Prediction endpoint. Place at: backend/app/routers/predictions.py

Uses the last ~10 metrics rows for a cluster to predict request_rate
~60 seconds ahead (Model A — see backend/app/ml/predictor.py), and
logs the prediction to the predictions table so accuracy can be
tracked over time (actual_request_rate gets backfilled later once
the real value has arrived — that's a separate follow-up job, not
built yet).
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db, SessionLocal
from ..models import Cluster, Metric, Prediction
from ..ml.predictor import predict_request_rate, InsufficientDataError, FETCH_ROWS, HORIZON_SECONDS

router = APIRouter(prefix="/clusters", tags=["predictions"])


@router.get("/{cluster_id}/predict")
async def predict_cluster_load(cluster_id: int, db: Session = Depends(get_db)):
    cluster = db.get(Cluster, cluster_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    rows = db.scalars(
        select(Metric)
        .where(Metric.cluster_id == cluster_id)
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

    try:
        predicted = predict_request_rate(rows_chronological)
    except InsufficientDataError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Log the prediction so accuracy can be evaluated later once the
    # real request_rate for this future timestamp has been collected.
    with SessionLocal() as write_db:
        pred_row = Prediction(
            cluster_id=cluster_id,
            ts=datetime.now(timezone.utc),
            horizon_seconds=HORIZON_SECONDS,
            predicted_request_rate=predicted,
            actual_request_rate=None,
        )
        write_db.add(pred_row)
        write_db.commit()

    return {
        "cluster_id": cluster_id,
        "cluster_name": cluster.name,
        "predicted_request_rate": predicted,
        "horizon_seconds": HORIZON_SECONDS,
        "model": "xgboost_live_only_v2",
    }