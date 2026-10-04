"""
Decision endpoints. Place at: backend/app/routers/decisions.py
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Cluster, Decision
from ..orchestration.decision import decide_scaling_action

router = APIRouter(prefix="/clusters", tags=["decisions"])


@router.get("/{cluster_id}/decision")
def preview_decision(cluster_id: int, commit: bool = False, db: Session = Depends(get_db)):
    """What would the orchestrator do right now? commit=false (default) is a
    read-only preview; commit=true also logs it to the decisions table."""
    if not db.get(Cluster, cluster_id):
        raise HTTPException(status_code=404, detail="Cluster not found")
    return decide_scaling_action(cluster_id, commit=commit).to_dict()


@router.get("/{cluster_id}/decisions")
def decision_history(cluster_id: int, limit: int = 20, db: Session = Depends(get_db)):
    if not db.get(Cluster, cluster_id):
        raise HTTPException(status_code=404, detail="Cluster not found")
    rows = db.scalars(
        select(Decision).where(Decision.cluster_id == cluster_id)
        .order_by(Decision.ts.desc()).limit(min(limit, 200))
    ).all()
    return [
        {"ts": r.ts, "source": r.source, "action": r.action, "prev_pods": r.prev_pods,
         "next_pods": r.next_pods, "predicted_value": r.predicted_value,
         "confidence": r.confidence, "reasoning": r.reasoning}
        for r in rows
    ]