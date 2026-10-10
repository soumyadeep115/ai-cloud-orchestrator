// Mirrors the constants in backend/app/orchestration/decision.py.
// If you retune the backend, change them here too so the charts stay honest.
export const REQ_PER_REPLICA = 4.0;
export const MIN_REPLICAS = 2;
export const MAX_REPLICAS = 10;
// Live scaling hard cap: ACTUATE_MAX_REPLICAS env var in backend/app/orchestration/actuator.py (default 6).
// Raise it in the backend (up to MAX_REPLICAS) and change it here to match.
export const LIVE_MAX_REPLICAS = 6;
export const SCALE_UP_UTIL = 0.8;
export const SCALE_DOWN_UTIL = 0.3;
export const FORECAST_HORIZON_S = 60;

export const DEFAULT_SLO_MS = 200; // latency objective line (editable in the UI)

// The poller writes one metrics row every ~15s.
export const ROW_SECONDS = 15;
export const RANGES = [
  { label: "15m", limit: 60 },
  { label: "30m", limit: 120 },
  { label: "1h", limit: 240 },
  { label: "2h", limit: 480 },
  { label: "6h", limit: 1000 },
];

export const REFRESH_OPTIONS = [
  { label: "5s", ms: 5000 },
  { label: "15s", ms: 15000 },
  { label: "30s", ms: 30000 },
  { label: "Off", ms: 0 },
];

export const COLORS = {
  cpu: "#5FD4D0",
  memory: "#FFB454",
  latency: "#FB7185",
  pods: "#A78BFA",
  rate: "#4ADE80",
  predicted: "#60A5FA",
  nodes: "#7C8B9B",
  up: "#4ADE80",
  down: "#FB7185",
  grid: "#1E2A35",
  axis: "#7C8B9B",
};
