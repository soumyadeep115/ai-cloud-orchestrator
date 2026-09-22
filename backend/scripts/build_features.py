"""
Feature engineering for the AI Cloud Orchestrator prediction model.

Pulls two datasets from Postgres:
  1. Live data: cluster-b only, source='live_poller' (real request_rate/latency)
  2. Trace data: source='alibaba_trace' (cpu/memory only, no request_rate)

Builds lag + rolling-window features for each, chronologically split into
train/test, and writes four CSVs plus a naive baseline error so you have
a number for XGBoost to beat.

Usage:
    python build_features.py

Output (written next to this script):
    live_train.csv, live_test.csv
    trace_train.csv, trace_test.csv
"""

import psycopg2
import pandas as pd
import numpy as np

DB_CONFIG = dict(
    host="localhost",
    port=5434,
    dbname="orchestrator",
    user="orchestrator",
    password="orchestrator_dev_password",
)

# How many past samples to look back for lag/rolling features
LAGS = [1, 2, 3]
ROLLING_WINDOW = 5          # samples (not minutes — intervals differ per source)

# Prediction horizon, in SAMPLES, set separately per source since their
# poll intervals differ (live: ~15s, trace: 300s already-grouped).
# LIVE_HORIZON=4 at a 15s interval ~= 60 seconds ahead — a genuinely
# useful lead time for proactive scaling, and far enough out that
# "predict = last value" stops being a near-free win.
LIVE_HORIZON = 4
TRACE_HORIZON = 1


def fetch_live_cluster_b(conn):
    query = """
        SELECT m.ts, m.cpu_percent, m.memory_percent, m.request_rate, m.latency_ms
        FROM metrics m
        JOIN clusters c ON c.id = m.cluster_id
        WHERE c.name = 'cluster-b' AND m.source = 'live_poller'
        ORDER BY m.ts ASC
    """
    df = pd.read_sql(query, conn)
    return df


def fetch_trace(conn):
    query = """
        SELECT ts, cpu_percent, memory_percent
        FROM metrics
        WHERE source = 'alibaba_trace'
        ORDER BY ts ASC
    """
    df = pd.read_sql(query, conn)
    return df


def add_lag_rolling_features(df, value_cols, target_col, horizon):
    """Adds lag_N and rolling mean/std columns for each value_col, plus
    a `target` column = target_col shifted `horizon` steps into the future."""
    df = df.copy()

    for col in value_cols:
        for lag in LAGS:
            df[f"{col}_lag{lag}"] = df[col].shift(lag)
        df[f"{col}_roll_mean"] = df[col].rolling(ROLLING_WINDOW).mean()
        df[f"{col}_roll_std"] = df[col].rolling(ROLLING_WINDOW).std()

    df["target"] = df[target_col].shift(-horizon)

    # Drop rows that don't have full lookback (start) or lookahead (end)
    df = df.dropna().reset_index(drop=True)
    return df


def chronological_split(df, test_frac=0.2):
    split_idx = int(len(df) * (1 - test_frac))
    return df.iloc[:split_idx].copy(), df.iloc[split_idx:].copy()


def naive_baseline_error(test_df, target_col_for_naive):
    """Naive baseline: predicted value = last observed value (persistence).
    Compares against the same 'target' column the model will be scored on."""
    naive_pred = test_df[target_col_for_naive]
    actual = test_df["target"]
    mae = np.mean(np.abs(naive_pred - actual))
    rmse = np.sqrt(np.mean((naive_pred - actual) ** 2))
    return mae, rmse


def main():
    conn = psycopg2.connect(**DB_CONFIG)

    # --- Live data (cluster-b): target = request_rate, HORIZON steps ahead ---
    live_raw = fetch_live_cluster_b(conn)
    print(f"Live (cluster-b) raw rows: {len(live_raw)}")

    live_feat = add_lag_rolling_features(
        live_raw,
        value_cols=["cpu_percent", "memory_percent", "request_rate", "latency_ms"],
        target_col="request_rate",
        horizon=LIVE_HORIZON,
    )
    print(f"Live rows after feature engineering (lookback/lookahead dropped): {len(live_feat)}")
    print(f"Live horizon: {LIVE_HORIZON} samples (~{LIVE_HORIZON * 15}s ahead at a 15s poll interval)")

    live_train, live_test = chronological_split(live_feat)
    live_train.to_csv("live_train.csv", index=False)
    live_test.to_csv("live_test.csv", index=False)
    print(f"Live train/test: {len(live_train)} / {len(live_test)}")

    mae, rmse = naive_baseline_error(live_test, "request_rate")
    print(f"Live naive baseline (predict = last request_rate) — MAE: {mae:.3f}, RMSE: {rmse:.3f}")

    # --- Trace data (Alibaba): no request_rate, so target = cpu_percent ahead ---
    # This dataset is for pretraining only — it teaches general load-pattern
    # shape, not this project's specific request_rate metric.
    trace_raw = fetch_trace(conn)
    print(f"\nTrace (alibaba) raw rows: {len(trace_raw)}")

    trace_feat = add_lag_rolling_features(
        trace_raw,
        value_cols=["cpu_percent", "memory_percent"],
        target_col="cpu_percent",
        horizon=TRACE_HORIZON,
    )
    print(f"Trace rows after feature engineering: {len(trace_feat)}")

    trace_train, trace_test = chronological_split(trace_feat)
    trace_train.to_csv("trace_train.csv", index=False)
    trace_test.to_csv("trace_test.csv", index=False)
    print(f"Trace train/test: {len(trace_train)} / {len(trace_test)}")

    mae_t, rmse_t = naive_baseline_error(trace_test, "cpu_percent")
    print(f"Trace naive baseline (predict = last cpu_percent) — MAE: {mae_t:.3f}, RMSE: {rmse_t:.3f}")

    conn.close()
    print("\nWrote: live_train.csv, live_test.csv, trace_train.csv, trace_test.csv")


if __name__ == "__main__":
    main()