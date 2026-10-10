# Orchestrator.control — Frontend

React + Vite + Tailwind 4 + Recharts dashboard for the AI Cloud Orchestrator backend.
Drop-in replacement for the old `frontend/` folder (same dependencies, same `.env`).

```bash
npm install
npm run dev        # http://localhost:5173
```

Backend URL: copy `.env.example` to `.env` and set `VITE_API_BASE_URL` (default `http://localhost:8000`).
The backend CORS list must include the origin the dev server uses (already `localhost:5173`).

## Sidebar views

| View | What it shows | Endpoints |
|---|---|---|
| Overview | all clusters, pod grid, pods vs req/s, p99 latency, last decision | `/clusters`, `/clusters/{id}/metrics`, `/decisions` |
| Pod Scaling | pod count over time with scale-up/down markers, estimated utilisation vs the 80%/30% thresholds, replica change log | `/metrics` |
| Latency | p99 now/avg/p95/max, editable objective line + breach %, latency vs pods, vs req/s, distribution | `/metrics` |
| Traffic & Forecast | req/s with the model's +60s forecast, pods needed, traffic vs pods | `/metrics`, `/predict` |
| Resources | CPU / memory / nodes, CPU vs pods | `/metrics` |
| Decisions | live read-only "what would the orchestrator do now" (regime, confidence, targets, reason) + decision history table | `/decision`, `/decisions` |

Top bar: time range (15m–6h of stored metrics) and auto-refresh interval (5s / 15s / 30s / off).
Sidebar: cluster picker with live pods + latency. The current view is kept in the URL hash.

## Notes

- `/predict` logs a row to the `predictions` table on every call, so the Traffic view calls it once a minute, only while that view is open.
- `/decision` is called with `commit=false` (preview only) — the UI never logs or applies a decision.
- Capacity constants (4 req/s per pod, 2–10 replicas, 80%/30% thresholds) live in `src/config.js`
  and mirror `backend/app/orchestration/decision.py`. Update both if you retune.
- The latency objective (default 200 ms) is editable on the Latency view and remembered in the browser.

## Pod count

The backend currently stores `count(kube_pod_info)` — every pod in the cluster, system pods included — as `pod_count`.
The orchestrator scales only `demo-workload` (2–10 replicas, live cap 6 by default).

- The frontend detects this (count above 10) and rebuilds the real replica series from the decision log
  (`prev_pods` = deployment size at each decision). This needs the decision loop running and covers the last ~200 decisions.
- To fix it at the source, change the `pod_count` query in `backend/app/prometheus.py` and `backend/app/poller.py` to
  `sum(kube_deployment_status_replicas{deployment="demo-workload"})` and restart the API and poller.
  Old rows keep the old values.

## Replica limits

`src/config.js` mirrors the backend: `MAX_REPLICAS = 10` (decision.py) and `LIVE_MAX_REPLICAS = 6`
(`ACTUATE_MAX_REPLICAS` env var, default 6, in actuator.py). To let the live loop go up to 10:
`$env:ACTUATE_MAX_REPLICAS="10"` before starting the loop, then set `LIVE_MAX_REPLICAS = 10` in `src/config.js`.
