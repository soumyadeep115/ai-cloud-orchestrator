export default function ClusterCard({ cluster, selected, onClick }) {
  const isHealthy = cluster.status === "healthy";

  const fmt = (v, unit = "") =>
    v === null || v === undefined
      ? "—"
      : `${Math.round(v * 10) / 10}${unit}`;

  return (
    <button
      onClick={onClick}
      className={`group w-full text-left rounded-xl border p-5 transition-all duration-200
        ${
          selected
            ? "border-accent bg-panel shadow-lg shadow-accent/10"
            : "border-hairline bg-panel/60 hover:border-accent/60 hover:bg-panel hover:-translate-y-0.5"
        }`}
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-5">
        <div>
          <div className="text-[10px] font-mono uppercase tracking-widest text-text-muted mb-1">
            Cluster
          </div>

          <h2 className="font-display font-semibold text-base text-text-primary">
            {cluster.name}
          </h2>
        </div>

        <div
          className={`flex items-center gap-2 rounded-full px-2.5 py-1 text-[10px] font-mono uppercase tracking-wide
            ${
              isHealthy
                ? "bg-good/10 text-good"
                : "bg-bad/10 text-bad"
            }`}
        >
          <span
            className={`w-2 h-2 rounded-full ${
              isHealthy ? "bg-good" : "bg-bad"
            }`}
          />

          {cluster.status}
        </div>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-2 gap-3">
        <Stat
          label="CPU Usage"
          value={fmt(cluster.cpu_percent, "%")}
        />

        <Stat
          label="Memory"
          value={fmt(cluster.memory_percent, "%")}
        />

        <Stat
          label="Pods"
          value={fmt(cluster.pod_count)}
        />

        <Stat
          label="Nodes"
          value={fmt(cluster.node_count)}
        />

        <Stat
          label="Requests / sec"
          value={fmt(cluster.request_rate)}
        />

        <Stat
          label="Latency"
          value={fmt(cluster.latency_ms, "ms")}
        />
      </div>

      {/* Selected indicator */}
      <div
        className={`mt-5 pt-3 border-t border-hairline text-[10px] font-mono transition-opacity
          ${
            selected
              ? "opacity-100 text-accent"
              : "opacity-0 group-hover:opacity-100 text-text-muted"
          }`}
      >
        {selected ? "● SELECTED CLUSTER" : "VIEW METRICS →"}
      </div>
    </button>
  );
}

function Stat({ label, value }) {
  return (
    <div className="rounded-lg border border-hairline bg-black/10 px-3 py-3">
      <div className="font-mono text-lg font-semibold text-text-primary tabular-nums">
        {value}
      </div>

      <div className="mt-1 text-[9px] text-text-muted uppercase tracking-wider">
        {label}
      </div>
    </div>
  );
}
