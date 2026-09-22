#!/usr/bin/env bash
# Runs every traffic profile back-to-back against a single cluster, unattended.
# Point this at cluster-b (your most stable end-to-end telemetry path) unless
# you've specifically stabilized cluster-a's port-forward too.
#
# Usage:
#   CLUSTER=cluster-b TARGET_URL=http://localhost:8081 \
#   K6_PROMETHEUS_RW_SERVER_URL=http://localhost:9091/api/v1/write \
#   bash generate-dataset.sh
#
# Make sure BEFORE running:
#   1. kubectl port-forward for the workload AND Prometheus are both up
#   2. python -m app.poller is running in another terminal (15s interval)
#   3. Leave this running for hours — close the laptop lid settings that
#      would sleep it, or run it inside WSL with the Windows machine set
#      to not sleep.

set -euo pipefail

CLUSTER="${CLUSTER:-cluster-b}"
TARGET_URL="${TARGET_URL:?Set TARGET_URL, e.g. http://localhost:8081}"
K6_PROMETHEUS_RW_SERVER_URL="${K6_PROMETHEUS_RW_SERVER_URL:?Set K6_PROMETHEUS_RW_SERVER_URL, e.g. http://localhost:9091/api/v1/write}"

# Order matters: idle first (baseline), then increasing complexity.
PROFILES=(idle long_ramp sustained periodic spike ramp idle)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for PROFILE in "${PROFILES[@]}"; do
    echo "=========================================="
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting profile: $PROFILE (cluster: $CLUSTER)"
    echo "=========================================="

    PROFILE="$PROFILE" \
    CLUSTER="$CLUSTER" \
    TARGET_URL="$TARGET_URL" \
    K6_PROMETHEUS_RW_SERVER_URL="$K6_PROMETHEUS_RW_SERVER_URL" \
    k6 run \
        --out experimental-prometheus-rw \
        "$SCRIPT_DIR/traffic.js" \
        || echo "[$(date '+%Y-%m-%d %H:%M:%S')] Profile $PROFILE exited non-zero, continuing anyway"

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Finished profile: $PROFILE"
    echo "Cooling off for 60s before next profile..."
    sleep 60
done

echo "=========================================="
echo "Dataset generation run complete."
echo "Check row count: SELECT COUNT(*) FROM metrics WHERE cluster_id = (SELECT id FROM clusters WHERE name = '$CLUSTER');"
echo "=========================================="