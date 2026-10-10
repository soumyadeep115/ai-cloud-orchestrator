import { fmt } from "../../lib/format";

export default function ClusterCard({ cluster, selected, onClick }) {
  const healthy = cluster.status === "healthy";
  return (
    <button
      onClick={onClick}
      className={`text-left rounded-lg border p-4 transition ${
        selected ? "border-accent bg-panel" : "border-hairline bg-panel/60 hover:border-text-muted"
      }`}
    >
      <div className="flex items-center justify-between mb-3">
        <span className="font-mono text-sm text-text-muted">{cluster.name}</span>
        <span className={`flex items-center gap-1.5 text-xs font-mono uppercase ${healthy ? "text-good" : "text-bad"}`}>
          <span className={`w-1.5 h-1.5 rounded-full ${healthy ? "bg-good" : "bg-bad"}`} />
          {cluster.status}
        </span>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <Mini label="Pods (cluster)" value={fmt(cluster.pod_count, 0)} tone="text-violet" />
        <Mini label="Latency p99" value={fmt(cluster.latency_ms, 0, "ms")} tone="text-bad" />
        <Mini label="Req/s" value={fmt(cluster.request_rate)} tone="text-good" />
        <Mini label="CPU" value={fmt(cluster.cpu_percent, 0, "%")} />
        <Mini label="Memory" value={fmt(cluster.memory_percent, 0, "%")} />
        <Mini label="Nodes" value={fmt(cluster.node_count, 0)} />
      </div>
    </button>
  );
}

function Mini({ label, value, tone = "text-text-primary" }) {
  return (
    <div>
      <div className={`font-mono text-lg font-medium tabular-nums ${tone}`}>{value}</div>
      <div className="text-[10px] text-text-muted uppercase tracking-wide">{label}</div>
    </div>
  );
}
