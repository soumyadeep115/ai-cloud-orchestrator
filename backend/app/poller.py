import asyncio
import logging
import os
from datetime import datetime, timezone

import httpx
from sqlalchemy import text

from app.database import SessionLocal


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


POLL_INTERVAL_SECONDS = int(
    os.getenv("POLL_INTERVAL_SECONDS", "15")
)


CLUSTERS = {
    "cluster-a": os.getenv(
        "PROMETHEUS_CLUSTER_A",
        "http://localhost:9090",
    ),
    "cluster-b": os.getenv(
        "PROMETHEUS_CLUSTER_B",
        "http://localhost:9091",
    ),
    "cluster-c": os.getenv(
        "PROMETHEUS_CLUSTER_C",
        "http://localhost:9092",
    ),
}


async def query_prometheus(
    client: httpx.AsyncClient,
    prometheus_url: str,
    query: str,
):
    url = f"{prometheus_url.rstrip('/')}/api/v1/query"

    response = await client.get(
        url,
        params={"query": query},
        timeout=10.0,
    )

    response.raise_for_status()

    data = response.json()

    if data.get("status") != "success":
        raise RuntimeError(
            f"Prometheus query failed: {data}"
        )

    return data["data"]["result"]


def extract_value(result, default=None):
    if not result:
        return default

    try:
        return float(result[0]["value"][1])
    except (
        KeyError,
        IndexError,
        TypeError,
        ValueError,
    ):
        return default


async def collect_cluster_metrics(
    client: httpx.AsyncClient,
    cluster_name: str,
    prometheus_url: str,
):
    queries = {
        "cpu_percent": """
            100 * (
                1 -
                avg(
                    rate(
                        node_cpu_seconds_total{
                            mode="idle"
                        }[5m]
                    )
                )
            )
        """,

        "memory_percent": """
            100 * (
                1 -
                (
                    sum(node_memory_MemAvailable_bytes)
                    /
                    sum(node_memory_MemTotal_bytes)
                )
            )
        """,

        "pod_count": """
            count(kube_pod_info)
        """,

        "node_count": """
            count(kube_node_info)
        """,

        "request_rate": """
            sum(
                rate(
                    k6_http_reqs_total[1m]
                )
            )
        """,

        "p99_latency_ms": """
            1000 * avg(
                k6_http_req_duration_p99
            )
        """,
    }

    metrics = {}

    for metric_name, query in queries.items():
        try:
            result = await query_prometheus(
                client,
                prometheus_url,
                query,
            )

            metrics[metric_name] = extract_value(
                result
            )

        except Exception as exc:
            logger.warning(
                "%s | Failed to collect %s: %s",
                cluster_name,
                metric_name,
                exc,
            )

            metrics[metric_name] = None

    return metrics


def get_cluster_id(
    db,
    cluster_name: str,
):
    result = db.execute(
        text(
            """
            SELECT id
            FROM clusters
            WHERE name = :name
            """
        ),
        {"name": cluster_name},
    )

    row = result.fetchone()

    return row[0] if row else None


def save_metrics(
    cluster_name: str,
    metrics: dict,
):
    db = SessionLocal()

    try:
        cluster_id = get_cluster_id(
            db,
            cluster_name,
        )

        if cluster_id is None:
            logger.warning(
                "Cluster %s does not exist in PostgreSQL",
                cluster_name,
            )
            return

        db.execute(
            text(
                """
                INSERT INTO metrics (
                    cluster_id,
                    ts,
                    cpu_percent,
                    memory_percent,
                    request_rate,
                    latency_ms,
                    pod_count,
                    node_count
                )
                VALUES (
                    :cluster_id,
                    :ts,
                    :cpu_percent,
                    :memory_percent,
                    :request_rate,
                    :latency_ms,
                    :pod_count,
                    :node_count
                )
                """
            ),
            {
                "cluster_id": cluster_id,
                "ts": datetime.now(timezone.utc),
                "cpu_percent": metrics["cpu_percent"],
                "memory_percent": metrics["memory_percent"],
                "request_rate": metrics["request_rate"],
                "latency_ms": metrics["p99_latency_ms"],
                "pod_count": (
                    int(metrics["pod_count"])
                    if metrics["pod_count"] is not None
                    else None
                ),
                "node_count": (
                    int(metrics["node_count"])
                    if metrics["node_count"] is not None
                    else None
                ),
            },
        )

        db.commit()

        logger.info(
            "%s | metrics saved | "
            "CPU=%.2f%% | "
            "MEM=%.2f%% | "
            "RequestRate=%.2f req/s | "
            "P99Latency=%.2f ms | "
            "Pods=%s | "
            "Nodes=%s",
            cluster_name,
            (
                metrics["cpu_percent"]
                if metrics["cpu_percent"] is not None
                else 0
            ),
            (
                metrics["memory_percent"]
                if metrics["memory_percent"] is not None
                else 0
            ),
            (
                metrics["request_rate"]
                if metrics["request_rate"] is not None
                else 0
            ),
            (
                metrics["p99_latency_ms"]
                if metrics["p99_latency_ms"] is not None
                else 0
            ),
            metrics["pod_count"],
            metrics["node_count"],
        )

    except Exception:
        db.rollback()

        logger.exception(
            "Failed to save metrics for %s",
            cluster_name,
        )

    finally:
        db.close()


async def poll_once():
    async with httpx.AsyncClient() as client:
        for cluster_name, prometheus_url in CLUSTERS.items():

            try:
                metrics = await collect_cluster_metrics(
                    client,
                    cluster_name,
                    prometheus_url,
                )

                save_metrics(
                    cluster_name,
                    metrics,
                )

            except Exception:
                logger.exception(
                    "Polling failed for %s",
                    cluster_name,
                )


async def run_poller():
    logger.info(
        "Starting metrics poller | interval=%ss",
        POLL_INTERVAL_SECONDS,
    )

    while True:
        try:
            await poll_once()

        except Exception:
            logger.exception(
                "Unexpected poller error"
            )

        await asyncio.sleep(
            POLL_INTERVAL_SECONDS
        )


if __name__ == "__main__":
    asyncio.run(run_poller())