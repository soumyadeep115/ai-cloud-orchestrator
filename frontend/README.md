# Orchestrator Frontend — Basic Version (Phase 1)

A minimal React dashboard that polls your real FastAPI backend every 5s
and shows live cluster status + a metrics history chart. Matched exactly
to your current `/clusters` and `/clusters/{id}/metrics` response shapes.

```

## Run it

```bash
npm install
npm run dev
```

By default it points at `http://localhost:8000` (your FastAPI backend's
usual port). If your backend runs elsewhere, copy `.env.example` to
`.env` and change `VITE_API_BASE_URL`.

## What it does

- Polls `GET /clusters` every 5s → renders a card per cluster (status,
  CPU%, memory%, pod/node count, request rate, latency)
- Click a card to select it → polls `GET /clusters/{id}/metrics` every
  5s → plots CPU / Memory / Latency history with Recharts
- Shows a clear inline error if the API is unreachable (most likely
  cause: the CORS fix above, or the backend not running)

## What it deliberately doesn't do yet

No decision log, no threshold-vs-ML comparison, no cost panel. This frontend only covers what Phase 1 actually has:
live cluster + metrics monitoring. Extend it once those endpoints exist
rather than building UI for data that doesn't exist server-side yet.

## File guide

- `src/api.js` — the only file that knows about your backend's URL and
  response shapes. Update here first if the API changes.
- `src/App.jsx` — polling logic + layout
- `src/components/ClusterCard.jsx`, `MetricsChart.jsx`
