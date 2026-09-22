import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from "recharts";

export default function MetricsChart({ clusterName, metrics }) {
  if (!metrics || metrics.length === 0) {
    return (
      <div className="rounded-lg border border-hairline bg-panel p-6 text-sm text-text-muted font-mono">
        No metrics stored yet for {clusterName ?? "this cluster"} — the poller writes a new row every 15s, check back shortly.
      </div>
    );
  }

  const data = metrics.map((m) => ({
    time: new Date(m.timestamp).toLocaleTimeString(),
    cpu: m.cpu_percent,
    memory: m.memory_percent,
    latency: m.latency_ms,
  }));

  return (
    <div className="rounded-lg border border-hairline bg-panel p-5">
      <div className="text-xs font-mono uppercase tracking-wider text-text-muted mb-4">
        {clusterName} — CPU / Memory / Latency history
      </div>
      <div style={{ width: "100%", height: 280 }}>
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 4, right: 12, left: -12, bottom: 0 }}>
            <CartesianGrid stroke="#1E2A35" strokeDasharray="3 5" vertical={false} />
            <XAxis dataKey="time" tick={{ fill: "#7C8B9B", fontSize: 11 }} axisLine={{ stroke: "#1E2A35" }} tickLine={false} />
            <YAxis tick={{ fill: "#7C8B9B", fontSize: 11 }} axisLine={false} tickLine={false} width={40} />
            <Tooltip
              contentStyle={{ background: "#10161D", border: "1px solid #1E2A35", fontSize: 12 }}
              labelStyle={{ color: "#7C8B9B" }}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Line type="monotone" dataKey="cpu" name="CPU %" stroke="#5FD4D0" strokeWidth={2} dot={false} isAnimationActive={false} />
            <Line type="monotone" dataKey="memory" name="Memory %" stroke="#FFB454" strokeWidth={2} dot={false} isAnimationActive={false} />
            <Line type="monotone" dataKey="latency" name="Latency (ms)" stroke="#FB7185" strokeWidth={2} dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
