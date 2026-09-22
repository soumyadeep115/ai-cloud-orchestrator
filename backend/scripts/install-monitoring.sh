#!/usr/bin/env bash
# Installs a lightweight Prometheus + kube-state-metrics into each of
# cluster-a/b/c. Deliberately skips Alertmanager and per-cluster Grafana
# (heavy, and you already have one React dashboard + can point one
# central Grafana at all three Prometheus instances later if needed) to
# keep resource usage sane across 3 clusters on one machine.
set -euo pipefail

CLUSTERS=("cluster-a" "cluster-b" "cluster-c")
NAMESPACE="monitoring"

command -v helm >/dev/null 2>&1 || { echo "helm not found. Install: https://helm.sh/docs/intro/install/"; exit 1; }
command -v kubectl >/dev/null 2>&1 || { echo "kubectl not found."; exit 1; }

echo "==> Adding prometheus-community Helm repo"
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null
helm repo update >/dev/null

for name in "${CLUSTERS[@]}"; do
    ctx="kind-$name"
    echo
    echo "==> Installing monitoring stack into $name"

    kubectl --context "$ctx" get namespace "$NAMESPACE" >/dev/null 2>&1 || \
        kubectl --context "$ctx" create namespace "$NAMESPACE"

    echo "    -> kube-state-metrics"
    helm upgrade --install kube-state-metrics prometheus-community/kube-state-metrics \
        --namespace "$NAMESPACE" \
        --kube-context "$ctx" \
        --wait --timeout 6m

    echo "    -> prometheus (server only, no alertmanager, no persistence)"
    helm upgrade --install prometheus prometheus-community/prometheus \
        --namespace "$NAMESPACE" \
        --kube-context "$ctx" \
        --set alertmanager.enabled=false \
        --set prometheus-pushgateway.enabled=false \
        --set prometheus-node-exporter.enabled=true \
        --set server.persistentVolume.enabled=false \
        --wait --timeout 6m

    echo "    -> $name monitoring stack ready"
done

cat <<'EOF'

All clusters have Prometheus + kube-state-metrics running.

To verify one cluster (repeat --context for cluster-b, cluster-c):

  kubectl --context kind-cluster-a -n monitoring port-forward svc/prometheus-server 9090:80

Then in another terminal:

  curl -s 'http://localhost:9090/api/v1/query?query=up' | python3 -m json.tool
  curl -s 'http://localhost:9090/api/v1/query?query=kube_pod_status_phase' | python3 -m json.tool

The first confirms Prometheus is scraping targets successfully (result
should be non-empty with value "1"). The second confirms kube-state-metrics
data — you should see demo-workload pods listed with phase="Running".
EOF