"""
Orchestrator decision layer (safeguards around a load prediction).

Place at: backend/app/orchestration/decision.py   (plus an empty __init__.py
in the same folder)

Design rule: this module never looks inside the model. It consumes only
  1. a predicted request_rate (req/s, ~60s ahead) or None, and
  2. raw recent metric rows (for the volatility signal).
Swapping/retraining the model changes nothing here except, possibly, the
CALIBRATION constants below.

Three safeguards:
  1. Bounded influence   - the final replica count may move at most
                           MAX_STEP_UP / MAX_STEP_DOWN per cycle.
  2. Reactive fallback   - a static-threshold rule on the CURRENT load is
                           always computed; it is the safety net and also
                           the "static threshold scaling" baseline.
  3. Volatility signal   - mean absolute request_rate jump over the last
                           few samples -> regime -> confidence -> how much
                           weight the prediction gets vs. the reactive rule.

The core function `decide()` is pure (no DB, no model import).
`decide_scaling_action(cluster_id)` is the thin DB/model wrapper.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional, Sequence

# =====================================================================
# CALIBRATION CONSTANTS  (the only things to re-tune; logic stays fixed)
# =====================================================================

# --- Volatility signal (jump-size based; same idea as sample_weight in
#     train_model.py: |request_rate - request_rate_lag1|) -------------
VOL_WINDOW_STEPS = 4          # number of most recent sample-to-sample jumps examined
VOL_MIN_JUMPS = 2             # fewer valid jumps than this -> regime "unknown"
VOL_MODERATE_JUMP = 1.0       # mean |jump| (req/s) at/above this -> "moderate"
VOL_VOLATILE_JUMP = 3.0       # mean |jump| (req/s) at/above this -> "volatile"

# --- Confidence = weight given to the prediction (0..1) ---------------
REGIME_CONFIDENCE = {
    "stable": 0.90,
    "moderate": 0.55,
    "volatile": 0.15,
    "unknown": 0.00,
}
CONFIDENCE_CUTOFF = 0.30          # confidence below this -> pure reactive fallback
MODEL_DOMINANT_CONFIDENCE = 0.80  # at/above this the source is labelled "model", else "blended"

# --- Capacity model (req/s <-> replicas) ------------------------------
REQ_PER_REPLICA = 4.0         # req/s one replica can serve at 100% utilisation
TARGET_UTILIZATION = 0.60     # predictive sizing aims for this utilisation
MIN_REPLICAS = 2
MAX_REPLICAS = 10
INITIAL_REPLICAS = 2          # assumed count when no decision has been logged yet

# --- Reactive (static threshold) rule ---------------------------------
SCALE_UP_UTILIZATION = 0.80   # utilisation above this -> scale up
SCALE_DOWN_UTILIZATION = 0.30 # utilisation below this -> scale down
REACTIVE_STEP = 1             # replicas added/removed per cycle by the static rule

# --- Bounded per-cycle influence --------------------------------------
MAX_STEP_UP = 2               # max replicas added in one cycle (any source)
MAX_STEP_DOWN = 1             # max replicas removed in one cycle (any source)

# --- Anti-flapping ----------------------------------------------------
SCALE_COOLDOWN_SECONDS = 120  # no scale-DOWN within this long of the last scaling action


# =====================================================================
# Data classes
# =====================================================================

@dataclass
class ScalerState:
    current_replicas: int = INITIAL_REPLICAS
    last_scale_ts: Optional[datetime] = None   # time of last non-hold decision


@dataclass
class VolatilitySignal:
    regime: str                 # stable | moderate | volatile | unknown
    mean_jump: Optional[float]  # mean |delta request_rate| over the window (req/s)
    n_jumps: int


@dataclass
class ScalingDecision:
    action: str                 # scale_up | scale_down | hold
    magnitude: int              # replicas changed (always >= 0)
    prev_replicas: int
    next_replicas: int
    source: str                 # model | blended | reactive_fallback
    regime: str
    confidence: float           # weight the prediction received (0..1)
    mean_jump: Optional[float]
    current_rate: Optional[float]
    predicted_rate: Optional[float]
    reactive_target: Optional[int]
    model_target: Optional[int]
    blended_target: Optional[int]
    step_capped: bool
    cooldown_blocked: bool
    reason: str
    ts: datetime

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ts"] = self.ts.isoformat()
        return d

    def to_db_fields(self) -> dict:
        """Map onto the existing `decisions` table CHECK constraints
        (source in 'threshold'|'ml'; action in 'scale_up'|'scale_down'|'no_action')."""
        return {
            "source": "threshold" if self.source == "reactive_fallback" else "ml",
            "action": "no_action" if self.action == "hold" else self.action,
            "prev_pods": self.prev_replicas,
            "next_pods": self.next_replicas,
            "predicted_value": self.predicted_rate,
            "confidence": self.confidence,
            "reasoning": self.reason,
        }


# =====================================================================
# Safeguard 3: volatility signal (raw metrics only - never the model)
# =====================================================================

def compute_volatility(rate_history: Sequence[Optional[float]]) -> VolatilitySignal:
    """rate_history: request_rate values, oldest -> newest (None allowed).
    Uses only the last VOL_WINDOW_STEPS + 1 samples."""
    recent = list(rate_history)[-(VOL_WINDOW_STEPS + 1):]
    jumps = [
        abs(b - a)
        for a, b in zip(recent, recent[1:])
        if a is not None and b is not None
    ]
    if len(jumps) < VOL_MIN_JUMPS:
        return VolatilitySignal("unknown", None, len(jumps))
    mean_jump = sum(jumps) / len(jumps)
    if mean_jump >= VOL_VOLATILE_JUMP:
        regime = "volatile"
    elif mean_jump >= VOL_MODERATE_JUMP:
        regime = "moderate"
    else:
        regime = "stable"
    return VolatilitySignal(regime, mean_jump, len(jumps))


# =====================================================================
# Safeguard 2: reactive static-threshold rule (also the baseline)
# =====================================================================

def reactive_target(current_rate: float, current_replicas: int) -> int:
    """Classic static-threshold scaling on CURRENT load."""
    util = current_rate / (current_replicas * REQ_PER_REPLICA)
    if util > SCALE_UP_UTILIZATION:
        return current_replicas + REACTIVE_STEP
    if util < SCALE_DOWN_UTILIZATION:
        return current_replicas - REACTIVE_STEP
    return current_replicas


def predictive_target(predicted_rate: float, current_replicas: int) -> int:
    """Size the cluster for the PREDICTED load. Uses the same dead-band as the
    reactive rule so a prediction inside the comfortable band means 'hold'."""
    util = predicted_rate / (current_replicas * REQ_PER_REPLICA)
    if SCALE_DOWN_UTILIZATION <= util <= SCALE_UP_UTILIZATION:
        return current_replicas
    return math.ceil(predicted_rate / (REQ_PER_REPLICA * TARGET_UTILIZATION))


# =====================================================================
# Core decision (pure)
# =====================================================================

def _clamp(x: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, x))


def decide(
    rows_chronological: Sequence[dict],
    predicted_rate: Optional[float],
    state: ScalerState,
    now: Optional[datetime] = None,
) -> ScalingDecision:
    """rows_chronological: dicts with at least 'request_rate' (oldest -> newest).
    predicted_rate: model output in req/s, or None if unavailable."""
    now = now or datetime.now(timezone.utc)
    cur = _clamp(state.current_replicas, MIN_REPLICAS, MAX_REPLICAS)

    rates = [r.get("request_rate") for r in rows_chronological]
    current_rate = next((x for x in reversed(rates) if x is not None), None)

    vol = compute_volatility(rates)

    if predicted_rate is not None and not math.isfinite(predicted_rate):
        predicted_rate = None

    # No current load reading at all -> nothing safe to act on.
    if current_rate is None:
        return ScalingDecision(
            action="hold", magnitude=0, prev_replicas=cur, next_replicas=cur,
            source="reactive_fallback", regime=vol.regime, confidence=0.0,
            mean_jump=vol.mean_jump, current_rate=None, predicted_rate=predicted_rate,
            reactive_target=None, model_target=None, blended_target=None,
            step_capped=False, cooldown_blocked=False,
            reason="No recent request_rate readings available; holding at "
                   f"{cur} replicas.",
            ts=now,
        )

    # Confidence = weight for the prediction; 0 if there is no prediction.
    confidence = REGIME_CONFIDENCE[vol.regime] if predicted_rate is not None else 0.0

    r_target = reactive_target(current_rate, cur)
    m_target = predictive_target(predicted_rate, cur) if predicted_rate is not None else None

    if confidence < CONFIDENCE_CUTOFF or m_target is None:
        source = "reactive_fallback"
        blended = r_target
    else:
        blended = math.floor(confidence * m_target + (1 - confidence) * r_target + 0.5)
        source = "model" if confidence >= MODEL_DOMINANT_CONFIDENCE else "blended"

    blended = _clamp(blended, MIN_REPLICAS, MAX_REPLICAS)

    # Safeguard 1: bound how far one cycle may move the replica count.
    nxt = _clamp(blended, cur - MAX_STEP_DOWN, cur + MAX_STEP_UP)
    step_capped = nxt != blended

    # Anti-flapping: block scale-down shortly after any scaling action.
    cooldown_blocked = False
    if nxt < cur and state.last_scale_ts is not None:
        if (now - state.last_scale_ts).total_seconds() < SCALE_COOLDOWN_SECONDS:
            nxt = cur
            cooldown_blocked = True

    action = "scale_up" if nxt > cur else "scale_down" if nxt < cur else "hold"

    reason = _explain(vol, confidence, source, current_rate, predicted_rate,
                      r_target, m_target, blended, cur, nxt, step_capped,
                      cooldown_blocked)

    return ScalingDecision(
        action=action, magnitude=abs(nxt - cur), prev_replicas=cur, next_replicas=nxt,
        source=source, regime=vol.regime, confidence=round(confidence, 3),
        mean_jump=None if vol.mean_jump is None else round(vol.mean_jump, 3),
        current_rate=round(current_rate, 3),
        predicted_rate=None if predicted_rate is None else round(predicted_rate, 3),
        reactive_target=r_target, model_target=m_target, blended_target=blended,
        step_capped=step_capped, cooldown_blocked=cooldown_blocked,
        reason=reason, ts=now,
    )


def _explain(vol, confidence, source, current_rate, predicted_rate, r_target,
             m_target, blended, cur, nxt, step_capped, cooldown_blocked) -> str:
    parts = []
    if vol.mean_jump is None:
        parts.append(f"Traffic regime is {vol.regime} (not enough valid recent samples).")
    else:
        parts.append(f"Traffic regime is {vol.regime} (mean jump {vol.mean_jump:.2f} req/s over "
                     f"last {vol.n_jumps} samples).")
    if source == "reactive_fallback":
        why = "no prediction available" if predicted_rate is None else \
              f"prediction confidence {confidence:.2f} is below the {CONFIDENCE_CUTOFF:.2f} cutoff"
        parts.append(f"Used reactive threshold rule because {why}: load {current_rate:.2f} req/s "
                     f"on {cur} replicas suggests {r_target}.")
    else:
        parts.append(f"Predicted load {predicted_rate:.2f} req/s (current {current_rate:.2f}) "
                     f"suggests {m_target} replicas; reactive rule suggests {r_target}; "
                     f"prediction weight {confidence:.2f} gives a {blended}-replica target ({source}).")
    if step_capped:
        parts.append(f"Per-cycle step limit applied (max +{MAX_STEP_UP}/-{MAX_STEP_DOWN}).")
    if cooldown_blocked:
        parts.append(f"Scale-down blocked by {SCALE_COOLDOWN_SECONDS}s cooldown.")
    parts.append(f"Result: {cur} -> {nxt} replicas.")
    return " ".join(parts)


# =====================================================================
# DB / model wrapper  (imports are lazy so decision.py can be imported
# and unit-tested without DATABASE_URL or the model file)
# =====================================================================

def decide_scaling_action(cluster_id: int, commit: bool = False) -> ScalingDecision:
    """Fetch recent metrics, ask the predictor, apply the safeguards.
    commit=False -> preview only. commit=True -> also log to `decisions`
    (dry-run: it updates the simulated replica count, it does not touch k8s)."""
    from sqlalchemy import select
    from ..database import SessionLocal
    from ..models import Decision, Metric

    try:  # a missing/broken model must degrade to reactive, not crash
        from ..ml.predictor import FETCH_ROWS, InsufficientDataError, predict_request_rate
    except Exception:
        FETCH_ROWS, InsufficientDataError, predict_request_rate = 10, Exception, None

    with SessionLocal() as db:
        rows = db.scalars(
            select(Metric).where(Metric.cluster_id == cluster_id)
            .order_by(Metric.ts.desc()).limit(max(FETCH_ROWS, VOL_WINDOW_STEPS + 1))
        ).all()
        rows_chrono = [
            {
                "cpu_percent": r.cpu_percent, "memory_percent": r.memory_percent,
                "request_rate": r.request_rate, "latency_ms": r.latency_ms,
            }
            for r in reversed(rows)
        ]

        last = db.scalars(
            select(Decision).where(Decision.cluster_id == cluster_id)
            .order_by(Decision.ts.desc()).limit(1)
        ).first()
        last_scale = db.scalars(
            select(Decision).where(Decision.cluster_id == cluster_id,
                                   Decision.action != "no_action")
            .order_by(Decision.ts.desc()).limit(1)
        ).first()
        state = ScalerState(
            current_replicas=last.next_pods if last and last.next_pods else INITIAL_REPLICAS,
            last_scale_ts=last_scale.ts if last_scale else None,
        )

        predicted = None
        if predict_request_rate is not None:
            try:
                predicted = predict_request_rate(rows_chrono)
            except InsufficientDataError:
                predicted = None

        decision = decide(rows_chrono, predicted, state)

        if commit:
            db.add(Decision(cluster_id=cluster_id, ts=decision.ts, **decision.to_db_fields()))
            db.commit()

    return decision