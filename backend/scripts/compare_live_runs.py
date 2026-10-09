"""
Compare live scaling runs (static vs ML) straight from the database.

Place at: backend/scripts/compare_live_runs.py
Run from backend/ (times are UTC, exactly as the k6 PowerShell block prints them):

  python scripts/compare_live_runs.py --cluster cluster-b --run static 2026-10-08T21:00:05 2026-10-08T21:07:30 --run ml 2026-10-08T21:20:10 2026-10-08T21:27:35

Repeat --run for more runs; runs with the same label are averaged.

Metrics, per run (rate = request_rate, cap = replicas * REQ_PER_REPLICA):
  start_replicas    replicas when the run began (should be 2 for every run)
  peak_rate         highest request_rate seen (a starved run shows a low peak)
  lead_s            first scale-up minus surge onset, in seconds (negative = BEFORE the surge)
  comfy_s           seconds from onset until load is back under the 80% scale-up line
  under_rows        samples with rate above total capacity (>100% utilisation)
  hot_rows          samples above the 80% scale-up line
  shortfall         sum over samples of (rate - capacity) where positive, req/s
  replica_min       replica-minutes used (cost proxy)
  waste_rows        samples under 25% utilisation with more than the minimum replicas
  moves / flaps     scale actions; scale-downs reversed by a scale-up within 120s
  ml_share          fraction of decisions where the model had any weight
Replicas are taken from the decisions (capped at the live limit). A replica is
counted as serving the moment it is decided; real pods take a few seconds to
start, which flatters both modes equally.
"""

import argparse
import math
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PAD_BEFORE_S = 60
PAD_AFTER_S = 180
ONSET_RATE = 6.0          # req/s at which the surge counts as started
MIN_VALID_PEAK = 10.0     # peak below this -> load generator was starved
GAP_WARN_S = 45           # metric gap longer than this inside a run -> warning
FLAP_WINDOW_S = 120
WASTE_UTIL = 0.25
HOT_UTIL = 0.80


def _consts():
    from app.orchestration import decision as D
    cap = min(D.MAX_REPLICAS, int(os.getenv("ACTUATE_MAX_REPLICAS", "6")))
    return D.REQ_PER_REPLICA, D.MIN_REPLICAS, cap


def load(cluster_name, lo, hi):
    from sqlalchemy import select
    from app.database import SessionLocal
    from app.models import Cluster, Decision, Metric

    with SessionLocal() as db:
        cid = db.scalar(select(Cluster.id).where(Cluster.name == cluster_name))
        if cid is None:
            raise SystemExit(f"cluster '{cluster_name}' not found")
        m = db.execute(
            select(Metric.ts, Metric.request_rate)
            .where(Metric.cluster_id == cid, Metric.ts >= lo, Metric.ts <= hi)
            .order_by(Metric.ts)
        ).all()
        d = db.execute(
            select(Decision.ts, Decision.action, Decision.prev_pods,
                   Decision.next_pods, Decision.source)
            .where(Decision.cluster_id == cid, Decision.ts >= lo, Decision.ts <= hi)
            .order_by(Decision.ts)
        ).all()
    mdf = pd.DataFrame([tuple(r) for r in m], columns=["ts", "request_rate"])
    ddf = pd.DataFrame([tuple(r) for r in d],
                       columns=["ts", "action", "prev_pods", "next_pods", "source"])
    for df in (mdf, ddf):
        if len(df):
            df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return mdf, ddf


def analyse(t0, t1, mdf, ddf, req_per_replica, min_replicas, cap):
    """Pure function: returns (metrics_dict, warnings_list)."""
    warns = []
    if ddf.empty or mdf.empty:
        return None, ["no metrics/decisions in this window - was the loop and poller running?"]

    ddf = ddf.sort_values("ts").reset_index(drop=True)
    mdf = mdf.sort_values("ts").reset_index(drop=True)
    start_reps = int(ddf.loc[0, "prev_pods"]) if pd.notna(ddf.loc[0, "prev_pods"]) else min_replicas
    if start_reps != min_replicas:
        warns.append(f"run started from {start_reps} replicas (not {min_replicas}) - not directly comparable")

    # replicas in force at each metric sample (decision takes effect after it is made)
    dts = ddf["ts"].tolist()
    nxt = [min(int(x), cap) if pd.notna(x) else None for x in ddf["next_pods"]]

    def reps_at(ts):
        r = min(start_reps, cap)
        for t, n in zip(dts, nxt):
            if t <= ts:
                r = n if n is not None else r
            else:
                break
        return r

    rows = mdf.dropna(subset=["request_rate"]).copy()
    run_rows = rows[(rows["ts"] >= t0) & (rows["ts"] <= t1)]
    if run_rows.empty:
        return None, ["no request_rate samples inside the run - k6 data missing"]

    rows["reps"] = rows["ts"].map(reps_at)
    rows["cap_rate"] = rows["reps"] * req_per_replica
    rows["util"] = rows["request_rate"] / rows["cap_rate"]

    peak = float(run_rows["request_rate"].max())
    if peak < MIN_VALID_PEAK:
        warns.append(f"peak rate only {peak:.1f} req/s - load generator was probably starved; discard this run")

    gaps = run_rows["ts"].diff().dt.total_seconds().dropna()
    if len(gaps) and gaps.max() > GAP_WARN_S:
        warns.append(f"metrics gap of {gaps.max():.0f}s inside the run")

    onset_rows = rows[(rows["ts"] >= t0) & (rows["request_rate"] >= ONSET_RATE)]
    onset = onset_rows["ts"].iloc[0] if len(onset_rows) else None
    ups = ddf[(ddf["action"] == "scale_up") & (ddf["ts"] >= t0)]
    first_up = ups["ts"].iloc[0] if len(ups) else None

    lead_s = (first_up - onset).total_seconds() if (onset is not None and first_up is not None) else None

    comfy_s = None
    if onset is not None:
        after = rows[(rows["ts"] >= onset) & (rows["request_rate"] >= 0.9 * peak)]
        ok = after[after["util"] <= HOT_UTIL]
        if len(ok):
            comfy_s = (ok["ts"].iloc[0] - onset).total_seconds()

    win = rows[(rows["ts"] >= t0) & (rows["ts"] <= t1 + pd.Timedelta(seconds=PAD_AFTER_S))]
    dt = win["ts"].diff().dt.total_seconds().dropna()
    step = float(dt.median()) if len(dt) else 15.0

    under = win[win["util"] > 1.0]
    hot = win[win["util"] > HOT_UTIL]
    shortfall = float((win["request_rate"] - win["cap_rate"]).clip(lower=0).sum())
    replica_min = float(win["reps"].sum() * step / 60.0)
    waste = win[(win["util"] < WASTE_UTIL) & (win["reps"] > min_replicas)]

    dwin = ddf[ddf["ts"] >= t0].copy()
    # a decision only counts as a move if it changes the replicas that really
    # exist (decisions that ask for more than the live cap are no-ops)
    dwin["applied"] = [
        (min(int(n), cap) != min(int(p), cap)) if pd.notna(n) and pd.notna(p) else False
        for p, n in zip(dwin["prev_pods"], dwin["next_pods"])
    ]
    moves = int(dwin["applied"].sum())
    flaps = 0
    for dtm in dwin[(dwin["action"] == "scale_down") & dwin["applied"]]["ts"]:
        if ((dwin["action"] == "scale_up") & dwin["applied"] & (dwin["ts"] > dtm) &
                (dwin["ts"] <= dtm + pd.Timedelta(seconds=FLAP_WINDOW_S))).any():
            flaps += 1

    ml_share = float((dwin["source"] == "ml").mean()) if len(dwin) else 0.0

    out = {
        "start_replicas": start_reps,
        "peak_rate": round(peak, 1),
        "lead_s": None if lead_s is None else round(lead_s, 0),
        "comfy_s": None if comfy_s is None else round(comfy_s, 0),
        "under_rows": int(len(under)),
        "hot_rows": int(len(hot)),
        "shortfall": round(shortfall, 1),
        "replica_min": round(replica_min, 1),
        "waste_rows": int(len(waste)),
        "moves": moves,
        "flaps": flaps,
        "ml_share": round(ml_share, 2),
    }
    return out, warns


def _ts(s):
    t = pd.Timestamp(s)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def main():
    ap = argparse.ArgumentParser(description="Compare live static vs ML scaling runs")
    ap.add_argument("--cluster", default="cluster-b")
    ap.add_argument("--run", nargs=3, action="append", required=True,
                    metavar=("LABEL", "START_UTC", "END_UTC"))
    args = ap.parse_args()

    rpr, min_rep, cap = _consts()
    results = []
    for label, s, e in args.run:
        t0, t1 = _ts(s), _ts(e)
        mdf, ddf = load(args.cluster, t0 - pd.Timedelta(seconds=PAD_BEFORE_S),
                        t1 + pd.Timedelta(seconds=PAD_AFTER_S))
        res, warns = analyse(t0, t1, mdf, ddf, rpr, min_rep, cap)
        tag = f"{label} {s}"
        for w in warns:
            print(f"WARNING [{tag}]: {w}")
        if res is not None:
            results.append({"run": tag, "label": label, **res})

    if not results:
        raise SystemExit("no usable runs")

    df = pd.DataFrame(results)
    pd.set_option("display.width", 200)
    print("\nPER RUN")
    print(df.drop(columns=["label"]).to_string(index=False))

    num = [c for c in df.columns if c not in ("run", "label")]
    mean = df.groupby("label")[num].mean(numeric_only=True).round(1)
    mean.insert(0, "n_runs", df.groupby("label").size())
    print("\nMEAN PER LABEL")
    print(mean.to_string())
    print("\nlower is better for: under_rows, hot_rows, shortfall, replica_min, waste_rows, moves, flaps, comfy_s, lead_s (negative lead = scaled before the surge)")


if __name__ == "__main__":
    main()