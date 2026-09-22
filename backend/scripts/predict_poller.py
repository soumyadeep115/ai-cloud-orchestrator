"""
Repeatedly calls GET /clusters/{id}/predict every POLL_INTERVAL_SECONDS
for DURATION_MINUTES, so you can accumulate multiple live predictions
across a single k6 traffic run instead of hitting the endpoint by hand.

Each call is already logged server-side into the predictions table by
the endpoint itself — this script just triggers those calls on a timer
and prints what came back, so you can watch it working.

Run this ALONGSIDE a k6 run with real variation (periodic or long_ramp
recommended — avoid sustained/high-VU profiles, which caused scrape
contention issues in earlier testing).

Usage:
    python predict_poller.py
"""

import time
import requests
from datetime import datetime

API_URL = "http://localhost:8000/clusters/2/predict"
POLL_INTERVAL_SECONDS = 15  # tightened from 30s so short profiles (e.g. spike, ~2.7 min) get properly sampled
DURATION_MINUTES = 6        # spans before/during/after a spike run, not just its ~2.7 min duration

def main():
    end_time = time.time() + DURATION_MINUTES * 60
    call_count = 0
    success_count = 0
    fail_count = 0

    print(f"Polling {API_URL} every {POLL_INTERVAL_SECONDS}s for {DURATION_MINUTES} min...")
    print("Press Ctrl+C to stop early.\n")

    try:
        while time.time() < end_time:
            call_count += 1
            ts = datetime.now().strftime("%H:%M:%S")
            try:
                resp = requests.get(API_URL, timeout=10)
                if resp.status_code == 200:
                    success_count += 1
                    data = resp.json()
                    print(f"[{ts}] OK  predicted_request_rate={data['predicted_request_rate']:.3f}")
                else:
                    fail_count += 1
                    print(f"[{ts}] {resp.status_code}  {resp.text[:100]}")
            except requests.RequestException as e:
                fail_count += 1
                print(f"[{ts}] ERROR  {e}")

            time.sleep(POLL_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("\nStopped early by user.")

    print(f"\nDone. Total calls: {call_count}, successful: {success_count}, failed: {fail_count}")
    print("Run backfill_predictions.py once these predictions' horizons have passed (60s each).")


if __name__ == "__main__":
    main()