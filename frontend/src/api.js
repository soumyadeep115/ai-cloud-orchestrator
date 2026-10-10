const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
const REQUEST_TIMEOUT_MS = 20000;

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function fetchWithTimeout(url, { signal, ...opts } = {}) {
  const controller = new AbortController();
  // Forward the caller's abort (a newer poll started / component unmounted)
  // as well as our own timeout, so requests can never pile up.
  if (signal) signal.addEventListener("abort", () => controller.abort());
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    return await fetch(url, { ...opts, signal: controller.signal });
  } finally {
    clearTimeout(timeoutId);
  }
}

async function getJson(path, signal) {
  const res = await fetchWithTimeout(`${API_BASE}${path}`, { signal });
  if (!res.ok) {
    let detail = "";
    try {
      detail = (await res.json()).detail ?? "";
    } catch {
      /* body wasn't JSON */
    }
    throw new ApiError(`GET ${path} failed: ${res.status}${detail ? ` — ${detail}` : ""}`, res.status);
  }
  return res.json();
}

export const fetchClusters = (signal) => getJson("/clusters", signal);

export const fetchClusterMetrics = (id, limit = 60, signal) =>
  getJson(`/clusters/${id}/metrics?limit=${limit}`, signal);

// Read-only: what would the orchestrator do right now? (commit=false)
export const fetchDecisionPreview = (id, signal) => getJson(`/clusters/${id}/decision`, signal);

export const fetchDecisions = (id, limit = 50, signal) =>
  getJson(`/clusters/${id}/decisions?limit=${limit}`, signal);

// NOTE: every call to /predict also logs a row in the `predictions` table.
export const fetchPrediction = (id, signal) => getJson(`/clusters/${id}/predict`, signal);

export const fetchHealth = (signal) => getJson("/health", signal);
