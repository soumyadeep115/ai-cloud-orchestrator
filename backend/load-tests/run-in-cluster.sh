#!/usr/bin/env bash
# Usage: ./run-in-cluster.sh [profile] [cluster]
#   ./run-in-cluster.sh surge cluster-b
set -euo pipefail
PROFILE="${1:-smoke}"
CLUSTER="${2:-cluster-b}"
CTX="kind-${CLUSTER}"
DIR="$(cd "$(dirname "$0")" && pwd)"

kubectl --context "$CTX" -n default delete job k6-load --ignore-not-found
kubectl --context "$CTX" -n default create configmap k6-script \
  --from-file=traffic.js="$DIR/traffic.js" --dry-run=client -o yaml \
  | kubectl --context "$CTX" apply -f -

sed -e "s/__PROFILE__/${PROFILE}/" -e "s/value: \"cluster-b\"/value: \"${CLUSTER}\"/" \
  "$DIR/k6-job.yaml" | kubectl --context "$CTX" apply -f -

echo "Job started (profile=$PROFILE, cluster=$CLUSTER). Following logs..."
kubectl --context "$CTX" -n default wait --for=condition=ready pod -l app=k6-load --timeout=120s || true
kubectl --context "$CTX" -n default logs -f job/k6-load