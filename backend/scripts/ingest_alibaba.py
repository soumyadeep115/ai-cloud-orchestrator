"""
Ingest the Alibaba 2018 machine_usage trace (5-min grouped, from the
Zenodo mirror) into the metrics table as a new, clearly-labelled source.

Run this ONCE on your machine (not inside Docker) after:
  1. docker compose up -d   (Postgres must be running)
  2. pip install psycopg2-binary --break-system-packages   (if not installed)

Usage:
    python ingest_alibaba.py "C:\\Users\\Soumyadeep mukherjee\\OneDrive\\Desktop\\mini project ty\\machine_usage_days_1_to_8_grouped_300_seconds.csv"
"""

import sys
import csv
import datetime
import psycopg2

DB_CONFIG = dict(
    host="localhost",
    port=5434,          # matches your docker-compose.yml port mapping
    dbname="orchestrator",
    user="orchestrator",
    password="orchestrator_dev_password",
)

TRACE_CLUSTER_NAME = "alibaba-trace"
INTERVAL_SECONDS = 300  # the file is already grouped every 300s (5 min)


def get_or_create_trace_cluster(cur):
    """Alibaba rows need a real cluster_id (FK is NOT NULL). Create a
    dedicated 'alibaba-trace' cluster row once, reuse it on every run."""
    cur.execute("SELECT id FROM clusters WHERE name = %s", (TRACE_CLUSTER_NAME,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(
        "INSERT INTO clusters (name, status, region) VALUES (%s, %s, %s) RETURNING id",
        (TRACE_CLUSTER_NAME, "unknown", "alibaba-trace-2018"),
    )
    return cur.fetchone()[0]


def ensure_source_column(cur):
    cur.execute("""
        ALTER TABLE metrics
        ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'live_poller'
    """)


def main():
    if len(sys.argv) != 2:
        print("Usage: python ingest_alibaba.py <path-to-csv>")
        sys.exit(1)

    csv_path = sys.argv[1]

    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"Read {len(rows)} rows from {csv_path}")

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    ensure_source_column(cur)
    cluster_id = get_or_create_trace_cluster(cur)
    print(f"Using cluster_id={cluster_id} for source='alibaba_trace'")

    # No timestamp column in this file — synthesize one, spaced 5 min
    # apart, ending "now" so it reads as a recent 8-day window rather
    # than an arbitrary date in the past.
    now = datetime.datetime.now(datetime.timezone.utc)
    start_ts = now - datetime.timedelta(seconds=INTERVAL_SECONDS * (len(rows) - 1))

    insert_sql = """
        INSERT INTO metrics
            (cluster_id, ts, cpu_percent, memory_percent,
             request_rate, latency_ms, pod_count, node_count, source)
        VALUES (%s, %s, %s, %s, NULL, NULL, NULL, NULL, 'alibaba_trace')
    """

    inserted = 0
    for i, row in enumerate(rows):
        ts = start_ts + datetime.timedelta(seconds=INTERVAL_SECONDS * i)
        cpu = float(row["cpu_util_percent"])
        mem = float(row["mem_util_percent"])
        cur.execute(insert_sql, (cluster_id, ts, cpu, mem))
        inserted += 1

    conn.commit()
    print(f"Inserted {inserted} rows into metrics (source='alibaba_trace').")

    cur.execute("""
        SELECT COUNT(*), MIN(ts), MAX(ts)
        FROM metrics WHERE source = 'alibaba_trace'
    """)
    count, tmin, tmax = cur.fetchone()
    print(f"Verification: {count} alibaba_trace rows, {tmin} -> {tmax}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()