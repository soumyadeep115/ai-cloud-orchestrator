-- =====================================================================
-- AI Cloud Orchestrator — Database Schema
-- Covers Phase 1 (clusters, metrics) through Phase 3 (decisions,
-- predictions) so no migration/rewrite is needed later.
-- =====================================================================

-- ---------------------------------------------------------------------
-- clusters: one row per Kind cluster you spin up (2-3 for this project)
-- ---------------------------------------------------------------------
CREATE TABLE clusters (
    id          SERIAL PRIMARY KEY,
    name        TEXT UNIQUE NOT NULL,              -- e.g. 'cluster-a'
    status      TEXT NOT NULL DEFAULT 'unknown'     -- 'healthy' | 'degraded' | 'unreachable'
                CHECK (status IN ('healthy', 'degraded', 'unreachable', 'unknown')),
    region      TEXT,                               -- optional; simulate multi-region later if wanted
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- metrics: time-series snapshot per cluster, written every ~10-15s by
-- the background poller (Phase 1, step 6). This is what your Live
-- Metrics chart and historical-storage requirement both read from.
-- ---------------------------------------------------------------------
CREATE TABLE metrics (
    id              BIGSERIAL PRIMARY KEY,
    cluster_id      INT NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    cpu_percent     DOUBLE PRECISION,   -- 0-100
    memory_percent  DOUBLE PRECISION,   -- 0-100
    request_rate    DOUBLE PRECISION,   -- req/s, from Prometheus once wired (null in Phase 1 if no load gen yet)
    latency_ms      DOUBLE PRECISION,
    pod_count       INT,
    node_count      INT
);

-- Every query you'll make against metrics is "latest N rows for cluster X"
-- or "range for cluster X" — this index makes both fast.
CREATE INDEX idx_metrics_cluster_ts ON metrics (cluster_id, ts DESC);

-- ---------------------------------------------------------------------
-- decisions: scaling actions taken by either scheduler (Phase 3).
-- Empty until you build the threshold/ML schedulers — defined now so
-- the schema doesn't change when you get there.
-- ---------------------------------------------------------------------
CREATE TABLE decisions (
    id              BIGSERIAL PRIMARY KEY,
    cluster_id      INT REFERENCES clusters(id) ON DELETE SET NULL,
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    source          TEXT NOT NULL CHECK (source IN ('threshold', 'ml')),
    action          TEXT NOT NULL CHECK (action IN ('scale_up', 'scale_down', 'no_action', 'migrate', 'delay')),
    prev_pods       INT,
    next_pods       INT,
    predicted_value DOUBLE PRECISION,   -- predicted req/s that triggered this (ML only)
    confidence      DOUBLE PRECISION,   -- 0-1; null for threshold decisions (they don't have confidence)
    reasoning       TEXT,               -- human-readable explanation — this is what Ollama will generate later
    cost_estimate   DOUBLE PRECISION    -- $/hr at the moment of this decision
);

CREATE INDEX idx_decisions_cluster_ts ON decisions (cluster_id, ts DESC);

-- ---------------------------------------------------------------------
-- predictions: raw model outputs kept separate from decisions, so you
-- can later backfill actual_request_rate and compute MAE/RMSE without
-- touching the decisions table (which is about actions, not accuracy).
-- ---------------------------------------------------------------------
CREATE TABLE predictions (
    id                      BIGSERIAL PRIMARY KEY,
    cluster_id              INT NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
    ts                      TIMESTAMPTZ NOT NULL DEFAULT now(),
    horizon_seconds         INT NOT NULL,   -- how far ahead this prediction looks
    predicted_request_rate  DOUBLE PRECISION,
    actual_request_rate     DOUBLE PRECISION   -- filled in once the real value arrives
);

CREATE INDEX idx_predictions_cluster_ts ON predictions (cluster_id, ts DESC);