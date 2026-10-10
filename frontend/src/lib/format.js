export const isNum = (v) => typeof v === "number" && Number.isFinite(v);

export function fmt(v, digits = 1, unit = "") {
  if (!isNum(v)) return "—";
  const f = 10 ** digits;
  return `${Math.round(v * f) / f}${unit}`;
}

export const fmtMs = (v) => (!isNum(v) ? "—" : v >= 1000 ? `${(v / 1000).toFixed(2)} s` : `${Math.round(v * 10) / 10} ms`);

export const fmtTime = (t) =>
  new Date(t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });

export const fmtClock = (t) => new Date(t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });

export function timeAgo(t) {
  const s = Math.max(0, Math.round((Date.now() - new Date(t).getTime()) / 1000));
  if (s < 5) return "just now";
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}
