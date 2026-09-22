import asyncio
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

TIMEOUT = float(os.getenv("PROMETHEUS_TIMEOUT_SECONDS", "5"))


def prometheus_url(cluster_name: str) -> str | None:
    key = f"PROMETHEUS_{cluster_name.replace('-', '_').upper()}_URL"
    return os.getenv(key)


async def query(cluster_name: str, promql: str) -> float | None:
    base_url = prometheus_url(cluster_name)

    if not base_url:
        return None

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(
            f"{base_url.rstrip('/')}/api/v1/query",
            params={"query": promql},
        )

        response.raise_for_status()
        payload = response.json()

    if payload.get("status") != "success":
        raise RuntimeError(
            f"Prometheus query failed for {cluster_name}"
        )

    result = payload.get("data", {}).get("result", [])

    if not result:
        return None

    value = float(result[0]["value"][1])

    if value != value:
        return None

    return value


async def cluster_metrics(cluster_name: str) -> dict:
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

    async def safe_query(promql: str) -> float | None:
        try:
            return await query(cluster_name, promql)
        except (
            httpx.HTTPError,
            KeyError,
            ValueError,
            RuntimeError,
        ):
            return None

    names = list(queries.keys())

    results = await asyncio.gather(
        *(safe_query(queries[name]) for name in names)
    )

    return dict(zip(names, results))