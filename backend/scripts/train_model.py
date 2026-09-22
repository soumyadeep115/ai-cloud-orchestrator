"""
Trains the XGBoost workload-prediction model — v2, addressing two issues
found in the first run:

  1. Model A (live-only) was overfitting: 200 trees / depth 4 on only
     499 training rows. Fixed with a validation split carved out of the
     training data (chronologically, not shuffled) and early stopping,
     so training halts once validation error stops improving instead of
     memorizing noise.

  2. Model B (pretrain on trace, fine-tune on live) had a scale mismatch:
     pretraining target was cpu_percent (range ~16-79), fine-tuning
     target was request_rate (a much smaller range) — the warm-started
     trees stayed anchored to the wrong output scale. Fixed by
     standardizing (z-score) both targets before training and inverse-
     transforming predictions back to the real request_rate scale before
     computing MAE/RMSE, so pretraining and fine-tuning operate on a
     shared, comparable scale.

Requires: pip install xgboost scikit-learn --break-system-packages

Usage:
    python train_model.py
(Run after build_features.py has written live_train.csv / live_test.csv /
 trace_train.csv / trace_test.csv in the same folder.)
"""

import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.preprocessing import StandardScaler

FEATURE_PREFIX_LIVE = ["cpu_percent", "memory_percent", "request_rate", "latency_ms"]
FEATURE_PREFIX_TRACE = ["cpu_percent", "memory_percent"]


def compute_naive_baseline(test_df):
    """Recomputed here (not hardcoded) so it always matches whatever
    horizon build_features.py was last run with — avoids comparing
    against a stale number from a previous horizon setting."""
    naive_pred = test_df["request_rate"]
    actual = test_df["target"]
    mae = mean_absolute_error(actual, naive_pred)
    rmse = np.sqrt(mean_squared_error(actual, naive_pred))
    return mae, rmse


def feature_columns(df, prefixes):
    cols = []
    for p in prefixes:
        cols += [c for c in df.columns if c.startswith(p + "_lag") or c.startswith(p + "_roll")]
    return cols


def chronological_val_split(X, y, val_frac=0.2):
    """Carve a validation slice off the END of the training set for early
    stopping — chronological, never shuffled, same principle as the
    original train/test split."""
    split_idx = int(len(X) * (1 - val_frac))
    return X.iloc[:split_idx], X.iloc[split_idx:], y.iloc[:split_idx], y.iloc[split_idx:]


def evaluate(y_true, y_pred, label, naive_mae):
    mae = mean_absolute_error(y_true, y_pred)
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    vs_naive_mae = ((mae - naive_mae) / naive_mae) * 100
    verdict = "BEATS naive" if mae < naive_mae else "worse than naive"
    print(f"{label} — MAE: {mae:.3f}, RMSE: {rmse:.3f}  ({vs_naive_mae:+.1f}% vs naive MAE, {verdict})")
    return mae, rmse


def main():
    live_train = pd.read_csv("live_train.csv")
    live_test = pd.read_csv("live_test.csv")
    trace_train = pd.read_csv("trace_train.csv")
    trace_test = pd.read_csv("trace_test.csv")

    live_cols = feature_columns(live_train, FEATURE_PREFIX_LIVE)
    trace_cols = feature_columns(trace_train, FEATURE_PREFIX_TRACE)
    shared_cols = [c for c in live_cols if c in trace_cols]

    print(f"Live feature columns: {len(live_cols)}")
    print(f"Trace feature columns: {len(trace_cols)}")
    print(f"Shared (used for pretrain -> fine-tune): {len(shared_cols)}\n")

    naive_mae, naive_rmse = compute_naive_baseline(live_test)
    print(f"Naive baseline (recomputed for current horizon) — MAE: {naive_mae:.3f}, RMSE: {naive_rmse:.3f}\n")

    # ================= Model A: live-only, with early stopping =================
    X_live_train_full, y_live_train_full = live_train[live_cols], live_train["target"]
    X_live_test, y_live_test = live_test[live_cols], live_test["target"]

    X_tr, X_val, y_tr, y_val = chronological_val_split(X_live_train_full, y_live_train_full)

    model_scratch = xgb.XGBRegressor(
        n_estimators=500,          # high ceiling — early stopping decides the real number
        max_depth=3,               # shallower: less room to overfit on ~400 rows
        learning_rate=0.03,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=5,        # requires more samples per leaf, discourages memorizing single points
        reg_lambda=1.5,            # extra L2 regularization
        early_stopping_rounds=20,
        random_state=42,
        eval_metric="mae",
    )
    model_scratch.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)
    print(f"Model A stopped at {model_scratch.best_iteration} trees (of 500 max)")

    print("\n=== Model A: live-only (regularized + early stopping) ===")
    preds_a = model_scratch.predict(X_live_test)
    evaluate(y_live_test, preds_a, "Live-only XGBoost v2", naive_mae)
    model_scratch.save_model("scratch_model.json")

    # ================= Model B: pretrain on trace, fine-tune on live =================
    # Standardize both targets so pretraining (cpu_percent scale) and
    # fine-tuning (request_rate scale) share a comparable output range.
    trace_scaler = StandardScaler()
    y_trace_train_scaled = trace_scaler.fit_transform(
        trace_train[["target"]]
    ).ravel()

    live_scaler = StandardScaler()
    y_live_train_scaled = live_scaler.fit_transform(
        y_live_train_full.values.reshape(-1, 1)
    ).ravel()

    X_trace_train = trace_train[shared_cols]
    X_live_train_shared = live_train[shared_cols]
    X_live_test_shared = live_test[shared_cols]

    pretrain_model = xgb.XGBRegressor(
        n_estimators=150, max_depth=4, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, random_state=42,
    )
    pretrain_model.fit(X_trace_train, y_trace_train_scaled)
    pretrain_model.save_model("pretrained_trace_model.json")

    # Fine-tune on the SCALED live target, continuing from the pretrained
    # booster — now both stages are on the same z-scored output range.
    X_tr_ft, X_val_ft, y_tr_ft, y_val_ft = chronological_val_split(
        X_live_train_shared, pd.Series(y_live_train_scaled)
    )

    finetune_model = xgb.XGBRegressor(
        n_estimators=300, max_depth=3, learning_rate=0.02,
        subsample=0.8, colsample_bytree=0.8,
        min_child_weight=5, reg_lambda=1.5,
        early_stopping_rounds=20,
        random_state=42,
        eval_metric="mae",
    )
    finetune_model.fit(
        X_tr_ft, y_tr_ft,
        eval_set=[(X_val_ft, y_val_ft)],
        xgb_model="pretrained_trace_model.json",
        verbose=False,
    )
    print(f"Model B stopped at {finetune_model.best_iteration} trees (of 300 max)")

    # Predict in scaled space, then inverse-transform back to real request_rate units
    preds_b_scaled = finetune_model.predict(X_live_test_shared)
    preds_b = live_scaler.inverse_transform(preds_b_scaled.reshape(-1, 1)).ravel()

    print("\n=== Model B: pretrained on Alibaba trace, fine-tuned on live (scale-corrected) ===")
    print("NOTE: Model B only has access to cpu/memory-derived features (the trace has")
    print("no request_rate), so it lacks request_rate_lag1/2/3 — the features naive")
    print("itself effectively is. Model B losing to Model A here is expected, not a bug.")
    evaluate(y_live_test, preds_b, "Pretrained+fine-tuned XGBoost v2", naive_mae)

    finetune_model.save_model("finetuned_model.json")
    print("\nSaved: pretrained_trace_model.json, finetuned_model.json")

    # ================= Model C: feature stacking (the actual fix for B) =================
    # Instead of warm-starting a booster across mismatched feature spaces,
    # use the trace-pretrained model as a signal generator: score it on
    # live data's cpu/memory features, and feed that single extra column
    # into a fresh model alongside ALL of Model A's original features —
    # crucially including request_rate_lag1/2/3, which Model B never had
    # access to. This keeps naive's strongest signal available while still
    # injecting whatever general load-shape pattern the trace taught.
    print("\n=== Model C: stacked (trace-pretrained signal + full live features) ===")

    trace_signal_train_scaled = pretrain_model.predict(live_train[shared_cols])
    trace_signal_test_scaled = pretrain_model.predict(live_test[shared_cols])
    # Inverse-transform back to cpu_percent's real scale so it's an
    # interpretable, stable feature rather than an arbitrary z-score.
    trace_signal_train = trace_scaler.inverse_transform(
        trace_signal_train_scaled.reshape(-1, 1)
    ).ravel()
    trace_signal_test = trace_scaler.inverse_transform(
        trace_signal_test_scaled.reshape(-1, 1)
    ).ravel()

    X_stack_train = X_live_train_full.copy()
    X_stack_train["trace_cpu_trend_signal"] = trace_signal_train
    X_stack_test = X_live_test.copy()
    X_stack_test["trace_cpu_trend_signal"] = trace_signal_test

    X_tr_c, X_val_c, y_tr_c, y_val_c = chronological_val_split(X_stack_train, y_live_train_full)

    model_stacked = xgb.XGBRegressor(
        n_estimators=500, max_depth=3, learning_rate=0.03,
        subsample=0.8, colsample_bytree=0.8,
        min_child_weight=5, reg_lambda=1.5,
        early_stopping_rounds=20,
        random_state=42,
        eval_metric="mae",
    )
    model_stacked.fit(X_tr_c, y_tr_c, eval_set=[(X_val_c, y_val_c)], verbose=False)
    print(f"Model C stopped at {model_stacked.best_iteration} trees (of 500 max)")

    preds_c = model_stacked.predict(X_stack_test)
    evaluate(y_live_test, preds_c, "Stacked XGBoost (Model C)", naive_mae)
    model_stacked.save_model("stacked_model.json")
    print("Saved: stacked_model.json")


if __name__ == "__main__":
    main()