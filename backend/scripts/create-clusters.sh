#!/usr/bin/env bash
# Creates cluster-a, cluster-b, cluster-c (Kind) and deploys a trivial
# nginx workload into each so there's something for Prometheus to
# scrape in step 4. Cluster names MUST match db/seed.sql exactly.
set -euo pipefail

CLUSTERS=("cluster-a" "cluster-b" "cluster-c")

command -v kind >/dev/null 2>&1 || { echo "kind not found. Install: https://kind.sigs.k8s.io/docs/user/quick-start/#installation"; exit 1; }
command -v kubectl >/dev/null 2>&1 || { echo "kubectl not found. Install: https://kubernetes.io/docs/tasks/tools/"; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "docker not found or not running. Kind needs Docker running."; exit 1; }

for name in "${CLUSTERS[@]}"; do
    if kind get clusters 2>/dev/null | grep -qx "$name"; then
        echo "==> $name already exists, skipping creation"
    else
        echo "==> Creating cluster: $name"
        kind create cluster --name "$name"
    fi

    echo "==> Deploying trivial nginx workload into $name"
    kubectl --context "kind-$name" apply -f - <<'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: demo-workload
  labels:
    app: demo-workload
spec:
  replicas: 2
  selector:
    matchLabels:
      app: demo-workload
  template:
    metadata:
      labels:
        app: demo-workload
    spec:
      containers:
        - name: nginx
          image: nginx:alpine
          resources:
            requests:
              cpu: "50m"
              memory: "64Mi"
            limits:
              cpu: "200m"
              memory: "128Mi"
          ports:
            - containerPort: 80
---
apiVersion: v1
kind: Service
metadata:
  name: demo-workload
spec:
  selector:
    app: demo-workload
  ports:
    - port: 80
      targetPort: 80
EOF

    echo "==> Waiting for demo-workload pods to be ready in $name"
    kubectl --context "kind-$name" rollout status deployment/demo-workload --timeout=90s
    echo
done

echo "All clusters ready. Verify with:"
echo "  kind get clusters"
echo "  kubectl --context kind-cluster-a get pods"