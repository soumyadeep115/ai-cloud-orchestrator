const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
const REQUEST_TIMEOUT_MS = 20000;

async function fetchWithTimeout(url, { signal, ...opts } = {}) {
  const controller = new AbortController();
  // If the caller passed its own AbortSignal (from the polling effect),
  // forward its abort to our controller too, so either a timeout OR a
  // new poll starting cancels this one — nothing can pile up.
  if (signal) signal.addEventListener("abort", () => controller.abort());
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    return await fetch(url, { ...opts, signal: controller.signal });
  } finally {
    clearTimeout(timeoutId);
  }
}

export async function fetchClusters(signal) {
  const res = await fetchWithTimeout(`${API_BASE}/clusters`, { signal });
  if (!res.ok) throw new Error(`GET /clusters failed: ${res.status}`);
  return res.json();
}

export async function fetchClusterMetrics(id, limit = 60, signal) {
  const res = await fetchWithTimeout(`${API_BASE}/clusters/${id}/metrics?limit=${limit}`, { signal });
  if (!res.ok) throw new Error(`GET /clusters/${id}/metrics failed: ${res.status}`);
  return res.json();
}