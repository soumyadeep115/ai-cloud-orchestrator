#!/usr/bin/env bash
# Runs the `spike` k6 profile back-to-back N times, with a cooldown
# between each, and logs the exact UTC start/end of every burst to a
# CSV so a downstream script can pull exactly those rows from the
# metrics table — no more reading timestamps off scrollback by hand.
#
# Usage:
#   CLUSTER=cluster-b TARGET_URL=http://localhost:8081 \
#   K6_PROMETHEUS_RW_SERVER_URL=http://localhost:9091/api/v1/write \
#   N_BURSTS=6 COOLDOWN_SECONDS=45 \
#   bash generate-spike-dataset.sh
#
# Make sure BEFORE running:
#   1. Port-forwards (workload + Prometheus) for the cluster are up
#   2. python -m app.poller is running in another terminal
#   3. Nothing else heavy is running on the machine, if possible —
#      the isolated single-burst test showed contention drops
#      predictions during simultaneous k6+poller+multi-cluster load.

set -euo pipefail

CLUSTER="${CLUSTER:-cluster-b}"
TARGET_URL="${TARGET_URL:?Set TARGET_URL, e.g. http://localhost:8081}"
K6_PROMETHEUS_RW_SERVER_URL="${K6_PROMETHEUS_RW_SERVER_URL:?Set K6_PROMETHEUS_RW_SERVER_URL, e.g. http://localhost:9091/api/v1/write}"
N_BURSTS="${N_BURSTS:-6}"
COOLDOWN_SECONDS="${COOLDOWN_SECONDS:-45}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$SCRIPT_DIR/../scripts/spike_burst_log.csv"

if [ ! -f "$LOG_FILE" ]; then
    echo "cluster,start_utc,end_utc" > "$LOG_FILE"
fi

echo "Logging burst windows to: $LOG_FILE"

for i in $(seq 1 "$N_BURSTS"); do
    echo "=========================================="
    echo "Spike burst $i of $N_BURSTS (cluster: $CLUSTER)"
    echo "=========================================="

    START_UTC="$(date -u '+%Y-%m-%d %H:%M:%S')"

    PROFILE=spike \
    CLUSTER="$CLUSTER" \
    TARGET_URL="$TARGET_URL" \
    K6_PROMETHEUS_RW_SERVER_URL="$K6_PROMETHEUS_RW_SERVER_URL" \
    k6 run \
        --out experimental-prometheus-rw \
        "$SCRIPT_DIR/traffic.js" \
        || echo "Burst $i exited non-zero, continuing anyway"

    END_UTC="$(date -u '+%Y-%m-%d %H:%M:%S')"

    echo "$CLUSTER,$START_UTC,$END_UTC" >> "$LOG_FILE"
    echo "Burst $i window (UTC): $START_UTC -> $END_UTC"

    if [ "$i" -lt "$N_BURSTS" ]; then
        echo "Cooling off for ${COOLDOWN_SECONDS}s before next burst..."
        sleep "$COOLDOWN_SECONDS"
    fi
done

echo "=========================================="
echo "Done. $N_BURSTS spike bursts logged to $LOG_FILE"
echo "=========================================="