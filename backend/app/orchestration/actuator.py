"""
Live scaling actuator (Kubernetes Python client).

Place at: backend/app/orchestration/actuator.py

Reads / sets the replica count of one Deployment on a kind cluster.
Cluster name "cluster-b" -> kubeconfig context "kind-cluster-b".

Env (all optional):
  KUBE_NAMESPACE        default "default"
  KUBE_DEPLOYMENT       default "demo-workload"
  KUBE_CONTEXT_PREFIX   default "kind-"
  ACTUATE_MAX_REPLICAS  default 6   (hard cap for LIVE scaling; also capped by
                                     MAX_REPLICAS in decision.py)
"""

import os
from dataclasses import dataclass
from functools import lru_cache

from kubernetes import client, config

from .decision import MAX_REPLICAS, MIN_REPLICAS

NAMESPACE = os.getenv("KUBE_NAMESPACE", "default")
DEPLOYMENT = os.getenv("KUBE_DEPLOYMENT", "demo-workload")
CONTEXT_PREFIX = os.getenv("KUBE_CONTEXT_PREFIX", "kind-")
LIVE_MAX_REPLICAS = min(MAX_REPLICAS, int(os.getenv("ACTUATE_MAX_REPLICAS", "6")))
REQUEST_TIMEOUT_SECONDS = 10


class ActuationError(RuntimeError):
    """Any failure talking to the cluster (bad context, API down, no deployment)."""


@dataclass
class ReplicaStatus:
    desired: int   # spec.replicas
    ready: int     # status.readyReplicas


@lru_cache(maxsize=None)
def _apps_api(cluster_name: str) -> client.AppsV1Api:
    context = f"{CONTEXT_PREFIX}{cluster_name}"
    try:
        api_client = config.new_client_from_config(context=context)
    except Exception as exc:
        raise ActuationError(
            f"cannot load kubeconfig context '{context}': {exc}"
        ) from exc
    return client.AppsV1Api(api_client)


def get_status(cluster_name: str) -> ReplicaStatus:
    api = _apps_api(cluster_name)
    try:
        dep = api.read_namespaced_deployment(
            DEPLOYMENT, NAMESPACE, _request_timeout=REQUEST_TIMEOUT_SECONDS
        )
    except Exception as exc:
        raise ActuationError(
            f"cannot read deployment {NAMESPACE}/{DEPLOYMENT} on {cluster_name}: {exc}"
        ) from exc
    desired = dep.spec.replicas if dep.spec.replicas is not None else 1
    ready = dep.status.ready_replicas or 0
    return ReplicaStatus(desired=desired, ready=ready)


def get_replicas(cluster_name: str) -> int:
    """Desired replica count currently set on the deployment."""
    return get_status(cluster_name).desired


def clamp_live(replicas: int) -> int:
    """Apply the hard limits used for real scaling."""
    return max(MIN_REPLICAS, min(LIVE_MAX_REPLICAS, int(replicas)))


def set_replicas(cluster_name: str, replicas: int) -> int:
    """Scale the deployment. Returns the value actually applied (after clamping)."""
    target = clamp_live(replicas)
    api = _apps_api(cluster_name)
    try:
        api.patch_namespaced_deployment_scale(
            DEPLOYMENT,
            NAMESPACE,
            {"spec": {"replicas": target}},
            _request_timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        raise ActuationError(
            f"cannot scale {NAMESPACE}/{DEPLOYMENT} on {cluster_name} to {target}: {exc}"
        ) from exc
    return target