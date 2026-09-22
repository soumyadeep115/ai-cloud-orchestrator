export default function ClusterCard({ cluster, selected, onClick }) {
  const isHealthy = cluster.status === "healthy";
  const fmt = (v, unit = "") => (v === null || v === undefined ? "—" : `${Math.round(v * 10) / 10}${unit}`);

  return (
    <button
      onClick={onClick}
      className={`text-left rounded-lg border p-4 transition ${
        selected ? "border-accent bg-panel" : "border-hairline bg-panel/60 hover:border-text-muted"
      }`}
    >
      <div className="flex items-center justify-between mb-3">
        <span className="font-mono text-sm text-text-muted">{cluster.name}</span>
        <span className={`flex items-center gap-1.5 text-xs font-mono uppercase ${isHealthy ? "text-good" : "text-bad"}`}>
          <span className={`w-1.5 h-1.5 rounded-full ${isHealthy ? "bg-good" : "bg-bad"}`} />
          {cluster.status}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Stat label="CPU" value={fmt(cluster.cpu_percent, "%")} />
        <Stat label="Memory" value={fmt(cluster.memory_percent, "%")} />
        <Stat label="Pods" value={fmt(cluster.pod_count)} />
        <Stat label="Nodes" value={fmt(cluster.node_count)} />
        <Stat label="Req/s" value={fmt(cluster.request_rate)} />
        <Stat label="Latency" value={fmt(cluster.latency_ms, "ms")} />
      </div>
    </button>
  );
}

function Stat({ label, value }) {
  return (
    <div>
      <div className="font-mono text-lg font-medium text-text-primary tabular-nums">{value}</div>
      <div className="text-[10px] text-text-muted uppercase tracking-wide">{label}</div>
    </div>
  );
}
