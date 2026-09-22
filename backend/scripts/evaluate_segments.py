"""
Breaks down naive vs. Model A vs. Model C's error separately for "stable"
periods versus "transition" periods (large jumps in request_rate).

A "transition" row is defined as one where |request_rate - request_rate_lag1|
is in the top 25% of observed jumps in the test set — i.e. the biggest,
most sudden changes. Everything else is "stable".

Requires: scratch_model.json AND stacked_model.json AND
pretrained_trace_model.json (all saved by train_model.py — run that first)

Usage:
    python evaluate_segments.py
"""

import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.preprocessing import StandardScaler

FEATURE_PREFIX_LIVE = ["cpu_percent", "memory_percent", "request_rate", "latency_ms"]


def feature_columns(df, prefixes):
    cols = []
    for p in prefixes:
        cols += [c for c in df.columns if c.startswith(p + "_lag") or c.startswith(p + "_roll")]
    return cols


def mae_rmse(y_true, y_pred):
    mae = mean_absolute_error(y_true, y_pred)
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    return mae, rmse


def main():
    live_test = pd.read_csv("live_test.csv")
    trace_train = pd.read_csv("trace_train.csv")
    live_cols = feature_columns(live_test, FEATURE_PREFIX_LIVE)
    trace_cols = feature_columns(trace_train, ["cpu_percent", "memory_percent"])
    shared_cols = [c for c in live_cols if c in trace_cols]

    model_a = xgb.XGBRegressor()
    model_a.load_model("scratch_model.json")

    # Rebuild the same stacked feature the training script built — the
    # StandardScaler is deterministic given the same trace_train data,
    # so refitting it here reproduces the exact same signal.
    trace_scaler = StandardScaler()
    trace_scaler.fit(trace_train[["target"]])

    pretrain_model = xgb.XGBRegressor()
    pretrain_model.load_model("pretrained_trace_model.json")

    model_c = xgb.XGBRegressor()
    model_c.load_model("stacked_model.json")

    trace_signal_test_scaled = pretrain_model.predict(live_test[shared_cols])
    trace_signal_test = trace_scaler.inverse_transform(
        trace_signal_test_scaled.reshape(-1, 1)
    ).ravel()

    X_test_a = live_test[live_cols]
    X_test_c = live_test[live_cols].copy()
    X_test_c["trace_cpu_trend_signal"] = trace_signal_test

    y_true = live_test["target"]
    naive_pred = live_test["request_rate"]
    pred_a = model_a.predict(X_test_a)
    pred_c = model_c.predict(X_test_c)

    jump = (live_test["request_rate"] - live_test["request_rate_lag1"]).abs()
    threshold = jump.quantile(0.75)
    transition_mask = jump >= threshold
    stable_mask = ~transition_mask

    print(f"Test set: {len(live_test)} rows")
    print(f"Transition threshold (top 25% jump size): {threshold:.3f}")
    print(f"Transition rows: {transition_mask.sum()}, Stable rows: {stable_mask.sum()}\n")

    for label, mask in [("STABLE periods", stable_mask), ("TRANSITION periods", transition_mask)]:
        if mask.sum() == 0:
            print(f"{label}: no rows in this segment, skipping")
            continue
        n_mae, n_rmse = mae_rmse(y_true[mask], naive_pred[mask])
        a_mae, a_rmse = mae_rmse(y_true[mask], pred_a[mask])
        c_mae, c_rmse = mae_rmse(y_true[mask], pred_c[mask])
        print(f"--- {label} (n={mask.sum()}) ---")
        print(f"  Naive     — MAE: {n_mae:.3f}, RMSE: {n_rmse:.3f}")
        print(f"  Model A   — MAE: {a_mae:.3f}, RMSE: {a_rmse:.3f}")
        print(f"  Model C   — MAE: {c_mae:.3f}, RMSE: {c_rmse:.3f}")
        best_mae = min([("Naive", n_mae), ("Model A", a_mae), ("Model C", c_mae)], key=lambda x: x[1])
        best_rmse = min([("Naive", n_rmse), ("Model A", a_rmse), ("Model C", c_rmse)], key=lambda x: x[1])
        print(f"  Best MAE: {best_mae[0]} ({best_mae[1]:.3f})  |  Best RMSE: {best_rmse[0]} ({best_rmse[1]:.3f})\n")


if __name__ == "__main__":
    main()