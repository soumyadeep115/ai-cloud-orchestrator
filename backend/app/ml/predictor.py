"""
Loads the production model (Model A — live-only XGBoost, chosen over
Model B/C per the training comparison) once at import time, and builds
the same lag/rolling features used during training from a small window
of recent metrics rows.

Place this file at: backend/app/ml/predictor.py
Place the trained model at: backend/app/ml/production_model.json
    (copy scratch_model.json from wherever train_model.py was run, and
    rename it — this is the file that gets loaded here)
"""

import os
import pandas as pd
import xgboost as xgb

LAGS = [1, 2, 3]
ROLLING_WINDOW = 5
# Must match LIVE_HORIZON from build_features.py at training time —
# this is documentation only, the model itself doesn't need this value,
# but the API response uses it to label what horizon this prediction covers.
HORIZON_SECONDS = 60

VALUE_COLS = ["cpu_percent", "memory_percent", "request_rate", "latency_ms"]

# Rows needed to compute the largest lag + full rolling window for the
# most recent point: max(LAGS) + ROLLING_WINDOW - 1 = 3 + 5 - 1 = 7.
# Fetch a couple extra as a safety margin against any gaps.
MIN_ROWS_NEEDED = max(LAGS) + ROLLING_WINDOW - 1
FETCH_ROWS = MIN_ROWS_NEEDED + 3

_MODEL_PATH = os.path.join(os.path.dirname(__file__), "production_model.json")
_model = xgb.XGBRegressor()
_model.load_model(_MODEL_PATH)


def _feature_columns():
    cols = []
    for col in VALUE_COLS:
        for lag in LAGS:
            cols.append(f"{col}_lag{lag}")
        cols.append(f"{col}_roll_mean")
        cols.append(f"{col}_roll_std")
    return cols


FEATURE_COLUMNS = _feature_columns()


class InsufficientDataError(Exception):
    """Raised when there aren't enough recent rows to build features."""


def build_latest_feature_row(rows_chronological: list[dict]) -> pd.DataFrame:
    """rows_chronological: list of dicts (oldest -> newest), each with
    cpu_percent/memory_percent/request_rate/latency_ms keys — as pulled
    from the metrics table for one cluster, ordered by ts ascending.
    Returns a single-row DataFrame of features for the most recent point,
    or raises InsufficientDataError if there's not enough history."""
    if len(rows_chronological) < MIN_ROWS_NEEDED:
        raise InsufficientDataError(
            f"Need at least {MIN_ROWS_NEEDED} recent rows to predict, got {len(rows_chronological)}"
        )

    df = pd.DataFrame(rows_chronological)

    for col in VALUE_COLS:
        for lag in LAGS:
            df[f"{col}_lag{lag}"] = df[col].shift(lag)
        df[f"{col}_roll_mean"] = df[col].rolling(ROLLING_WINDOW).mean()
        df[f"{col}_roll_std"] = df[col].rolling(ROLLING_WINDOW).std()

    latest = df.iloc[[-1]][FEATURE_COLUMNS]

    if latest.isnull().any(axis=1).iloc[0]:
        raise InsufficientDataError(
            "Most recent rows contain NULLs (e.g. cluster was briefly "
            "unreachable) — cannot build a complete feature row yet."
        )

    return latest


def predict_request_rate(rows_chronological: list[dict]) -> float:
    features = build_latest_feature_row(rows_chronological)
    pred = _model.predict(features)[0]
    return max(0.0, float(pred))  # request_rate can't be negative