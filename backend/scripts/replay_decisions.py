"""
Replays logged spike bursts through the orchestrator and compares it with
pure static-threshold scaling on the SAME data.

Place at: backend/scripts/replay_decisions.py
Run from backend/:   python scripts/replay_decisions.py
Needs: scripts/live_train.csv, scripts/live_test.csv, scripts/spike_burst_log.csv
       and app/ml/production_model.json. No database required.

Both strategies start each burst at INITIAL_REPLICAS and run on simulated
replica counts (dry-run). The static baseline is the exact same code with the
prediction withheld (decide(..., predicted_rate=None)), so the ONLY difference
between the two columns is the model + safeguards.
"""

import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from app.orchestration import decision as D
from app.ml.predictor import FETCH_ROWS, InsufficientDataError, predict_request_rate

HERE = os.path.dirname(os.path.abspath(__file__))
PRE_S, POST_S = 120, 75          # replay window = burst start-120s .. end+75s
GAP_S = 120                      # a gap longer than this breaks the history
HORIZON_S, HORIZON_TOL_S = 60, 30
SATURATION_UTIL = 1.0            # realised load / capacity above this = under-provisioned
WASTE_UTIL = 0.25                # below this (above MIN_REPLICAS) = over-provisioned
VALUE_COLS = ["cpu_percent", "memory_percent", "request_rate", "latency_ms"]


def load_raw():
    parts = [pd.read_csv(os.path.join(HERE, f)) for f in ("live_train.csv", "live_test.csv")]
    df = pd.concat(parts)[["ts"] + VALUE_COLS]
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.drop_duplicates("ts").sort_values("ts").reset_index(drop=True)
    df["seg"] = (df["ts"].diff().dt.total_seconds() > GAP_S).cumsum()
    return df


def realised(df, i):
    t = df.loc[i, "ts"] + timedelta(seconds=HORIZON_S)
    cand = df[(df["seg"] == df.loc[i, "seg"]) & (df.index > i)]
    if cand.empty:
        return None
    j = (cand["ts"] - t).abs().idxmin()
    if abs((df.loc[j, "ts"] - t).total_seconds()) > HORIZON_TOL_S:
        return None
    return float(df.loc[j, "request_rate"])


def context(df, i):
    seg = df.loc[i, "seg"]
    lo = max(0, i - FETCH_ROWS + 1)
    ctx = df.loc[lo:i]
    ctx = ctx[ctx["seg"] == seg]
    return ctx[VALUE_COLS].to_dict("records")


def score(log):
    under = over = moves = 0
    replica_cycles = 0
    shortfall = 0.0
    n = 0
    prev = None
    for row in log:
        if row["realised"] is None:
            continue
        n += 1
        cap = row["next"] * D.REQ_PER_REPLICA
        replica_cycles += row["next"]
        util = row["realised"] / cap
        if util > SATURATION_UTIL:
            under += 1
            shortfall += row["realised"] - cap
        elif util < WASTE_UTIL and row["next"] > D.MIN_REPLICAS:
            over += 1
        if prev is not None and row["next"] != prev:
            moves += 1
        prev = row["next"]
    return dict(cycles=n, under=under, over=over, moves=moves,
                replica_cycles=replica_cycles, shortfall=round(shortfall, 1))


def main():
    df = load_raw()
    bursts = pd.read_csv(os.path.join(HERE, "spike_burst_log.csv"))
    bursts["s"] = pd.to_datetime(bursts["start_utc"], utc=True)
    bursts["e"] = pd.to_datetime(bursts["end_utc"], utc=True)

    all_orch, all_static = [], []
    used = 0
    for _, b in bursts.iterrows():
        w = df[(df["ts"] >= b.s - timedelta(seconds=PRE_S)) &
               (df["ts"] <= b.e + timedelta(seconds=POST_S))]
        if len(w) < 6:
            continue
        used += 1
        st_o = D.ScalerState()
        st_s = D.ScalerState()
        print(f"\n=== burst {b.s:%Y-%m-%d %H:%M} UTC  ({len(w)} samples) ===")
        print(f"{'time':8} {'rate':>5} {'pred':>5} {'regime':9} {'conf':>4} {'source':17} "
              f"{'orch':>7} {'static':>7} {'real+60s':>8}")
        for i in w.index:
            ctx = context(df, i)
            try:
                pred = predict_request_rate(ctx)
            except InsufficientDataError:
                pred = None
            now = df.loc[i, "ts"].to_pydatetime()
            do = D.decide(ctx, pred, st_o, now)
            ds = D.decide(ctx, None, st_s, now)
            real = realised(df, i)
            all_orch.append(dict(next=do.next_replicas, realised=real))
            all_static.append(dict(next=ds.next_replicas, realised=real))
            print(f"{now:%H:%M:%S} {do.current_rate:5.1f} "
                  f"{'' if pred is None else format(pred, '5.1f'):>5} {do.regime:9} "
                  f"{do.confidence:4.2f} {do.source:17} "
                  f"{do.prev_replicas:>2}->{do.next_replicas:<3} {ds.prev_replicas:>2}->{ds.next_replicas:<3} "
                  f"{'' if real is None else format(real, '8.1f'):>8}")
            for st, d in ((st_o, do), (st_s, ds)):
                st.current_replicas = d.next_replicas
                if d.action != "hold":
                    st.last_scale_ts = now
        # state is reset per burst; scoring accumulates across bursts

    print(f"\n{'='*70}\nSUMMARY over {used} bursts (scored on realised load ~{HORIZON_S}s ahead)")
    so, ss = score(all_orch), score(all_static)
    print(f"{'metric':32} {'orchestrator':>14} {'static only':>14}")
    labels = {
        "cycles": "scored cycles",
        "under": "under-provisioned cycles",
        "shortfall": "total req/s shortfall",
        "over": "over-provisioned cycles",
        "replica_cycles": "replica-cycles (cost proxy)",
        "moves": "scaling moves",
    }
    for k, lab in labels.items():
        print(f"{lab:32} {so[k]:>14} {ss[k]:>14}")


if __name__ == "__main__":
    main()