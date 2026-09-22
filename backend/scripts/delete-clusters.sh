#!/usr/bin/env bash
# Deletes all three clusters. Use when you need a clean slate
# (e.g. after changing the demo workload or before re-testing schema changes).
set -euo pipefail

CLUSTERS=("cluster-a" "cluster-b" "cluster-c")

for name in "${CLUSTERS[@]}"; do
    if kind get clusters 2>/dev/null | grep -qx "$name"; then
        echo "==> Deleting cluster: $name"
        kind delete cluster --name "$name"
    else
        echo "==> $name does not exist, skipping"
    fi
done