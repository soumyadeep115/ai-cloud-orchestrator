import { LIVE_MAX_REPLICAS, MIN_REPLICAS, REQ_PER_REPLICA } from "../config";
import { isNum } from "./format";

/** API rows -> chart rows with a numeric time axis and derived fields. */
export function normalizeMetrics(metrics) {
  if (!metrics) return [];
  return metrics.map((m) => {
    const pods = m.pod_count;
    const rate = m.request_rate;
    return {
      t: new Date(m.timestamp).getTime(),
      cpu: m.cpu_percent,
      memory: m.memory_percent,
      rate,
      latency: m.latency_ms,
      pods,
      nodes: m.node_count,
      // estimated utilisation, same capacity model the orchestrator uses
      util: isNum(rate) && isNum(pods) && pods > 0 ? (rate / (pods * REQ_PER_REPLICA)) * 100 : null,
    };
  });
}

export const values = (rows, key) => rows.map((r) => r[key]).filter(isNum);

export function mean(arr) {
  return arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : null;
}

export function percentile(arr, p) {
  if (!arr.length) return null;
  const s = [...arr].sort((a, b) => a - b);
  const idx = (s.length - 1) * p;
  const lo = Math.floor(idx);
  const hi = Math.ceil(idx);
  return s[lo] + (s[hi] - s[lo]) * (idx - lo);
}

export const latest = (rows, key) => {
  for (let i = rows.length - 1; i >= 0; i--) if (isNum(rows[i][key])) return rows[i][key];
  return null;
};

/** Replica-count changes actually observed in the metrics stream. */
export function podChanges(rows) {
  const out = [];
  let prev = null;
  for (const r of rows) {
    if (!isNum(r.pods)) continue;
    if (prev !== null && r.pods !== prev) out.push({ t: r.t, from: prev, to: r.pods, dir: r.pods > prev ? "up" : "down" });
    prev = r.pods;
  }
  return out;
}

/** Bucket latencies for a distribution chart. */
export function histogram(arr, buckets = 12) {
  if (arr.length < 2) return [];
  const min = Math.min(...arr);
  const max = Math.max(...arr);
  if (min === max) return [{ label: `${Math.round(min)}`, count: arr.length }];
  const step = (max - min) / buckets;
  const bins = Array.from({ length: buckets }, (_, i) => ({
    from: min + i * step,
    label: `${Math.round(min + i * step)}`,
    count: 0,
  }));
  for (const v of arr) bins[Math.min(buckets - 1, Math.floor((v - min) / step))].count++;
  return bins;
}

/**
 * The backend's pod_count is count(kube_pod_info): every pod in the cluster.
 * The decision log, however, records the real deployment size every cycle
 * (prev_pods = replicas at decision time). Rebuild the workload replica series
 * from it. Returns null when there is no usable decision history.
 */
export function withWorkloadReplicas(rows, decisions) {
  if (!rows.length || !decisions?.length) return null;
  const ds = decisions
    .filter((d) => isNum(d.prev_pods) && isNum(d.next_pods))
    .map((d) => ({ t: new Date(d.ts).getTime(), prev: d.prev_pods, next: d.next_pods }))
    .sort((a, b) => a.t - b.t);
  if (!ds.length) return null;
  const after = Math.max(MIN_REPLICAS, Math.min(LIVE_MAX_REPLICAS, ds[ds.length - 1].next));
  const startT = ds[0].t - 60000;
  let i = 0;
  return rows.map((r) => {
    if (r.t < startT) return { ...r, pods: null, util: null };
    while (i < ds.length && ds[i].t < r.t) i++;
    const pods = i < ds.length ? ds[i].prev : after;
    const util = isNum(r.rate) && pods > 0 ? (r.rate / (pods * REQ_PER_REPLICA)) * 100 : null;
    return { ...r, pods, util };
  });
}
