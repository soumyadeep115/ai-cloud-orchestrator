-- Run after schema.sql. Names must match the Kind cluster names you
-- create in Phase 1 step 3 (kind create cluster --name cluster-a, etc.)
-- so the poller can map Prometheus targets to the right row.

INSERT INTO clusters (name, status) VALUES
    ('cluster-a', 'unknown'),
    ('cluster-b', 'unknown'),
    ('cluster-c', 'unknown');