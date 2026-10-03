"""
Reads spike_burst_log.csv (written by generate-spike-dataset.sh) and
pulls exactly the metrics rows that fall inside a logged spike burst
window, across however many sessions you've run this over time —
so you can see your running total of real spike-labeled rows, and
export them for a future retraining pass.

Place at: backend/scripts/tag_spike_windows.py
Usage:
    python tag_spike_windows.py
"""

import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone
from sqlalchemy import select, and_

from app.database import SessionLocal
from app.models import Metric, Cluster

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "spike_burst_log.csv")
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "spike_labeled_metrics.csv")


def main():
    if not os.path.exists(LOG_FILE):
        print(f"No {LOG_FILE} found yet — run generate-spike-dataset.sh at least once first.")
        return

    db = SessionLocal()

    windows_by_cluster = {}
    with open(LOG_FILE, newline="") as f:
        for row in csv.DictReader(f):
            cluster_name = row["cluster"]
            start = datetime.strptime(row["start_utc"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            end = datetime.strptime(row["end_utc"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            windows_by_cluster.setdefault(cluster_name, []).append((start, end))

    print(f"Loaded {sum(len(w) for w in windows_by_cluster.values())} logged burst window(s) "
          f"across {len(windows_by_cluster)} cluster(s).\n")

    all_rows = []

    for cluster_name, windows in windows_by_cluster.items():
        cluster = db.scalar(select(Cluster).where(Cluster.name == cluster_name))
        if not cluster:
            print(f"WARNING: no cluster named '{cluster_name}' found, skipping its {len(windows)} window(s).")
            continue

        cluster_row_count = 0

        for start, end in windows:
            rows = db.scalars(
                select(Metric).where(
                    and_(
                        Metric.cluster_id == cluster.id,
                        Metric.ts >= start,
                        Metric.ts <= end,
                        Metric.request_rate.is_not(None),
                    )
                )
            ).all()
            cluster_row_count += len(rows)
            for r in rows:
                all_rows.append({
                    "cluster": cluster_name,
                    "ts": r.ts.isoformat(),
                    "cpu_percent": r.cpu_percent,
                    "memory_percent": r.memory_percent,
                    "request_rate": r.request_rate,
                    "latency_ms": r.latency_ms,
                    "pod_count": r.pod_count,
                    "node_count": r.node_count,
                })

        print(f"{cluster_name}: {cluster_row_count} spike-window rows across {len(windows)} burst(s)")

    if not all_rows:
        print("\nNo spike-window rows found yet.")
        db.close()
        return

    all_rows.sort(key=lambda r: r["ts"])

    with open(OUTPUT_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=all_rows[0].keys())
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"\nTotal spike-labeled rows: {len(all_rows)}")
    print(f"Written to: {OUTPUT_FILE}")
    print("\nFor reference, your original live-validation report noted only ~610 rows total "
          "and a small minority actually spike-labeled — compare that against the count above "
          "to see how much this closes the gap.")

    db.close()


if __name__ == "__main__":
    main()