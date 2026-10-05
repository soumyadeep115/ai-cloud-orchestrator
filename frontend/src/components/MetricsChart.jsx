import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";

export default function MetricsChart({ clusterName, metrics }) {
  if (!metrics || metrics.length === 0) {
    return (
      <div className="rounded-xl border border-hairline bg-panel p-6">
        <div className="flex items-center gap-3 mb-3">
          <span className="w-2 h-2 rounded-full bg-text-muted" />
          <span className="text-xs font-mono uppercase tracking-widest text-text-muted">
            Metrics unavailable
          </span>
        </div>

        <p className="text-sm text-text-muted font-mono leading-relaxed">
          No metrics stored yet for {clusterName ?? "this cluster"}.
          <br />
          The poller writes a new row every 15 seconds. Check back shortly.
        </p>
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
    <section className="rounded-xl border border-hairline bg-panel overflow-hidden">
      {/* Chart header */}
      <div className="px-5 py-4 border-b border-hairline flex items-center justify-between">
        <div>
          <div className="text-[10px] font-mono uppercase tracking-widest text-text-muted mb-1">
            Performance
          </div>

          <h3 className="text-sm font-semibold text-text-primary">
            {clusterName} metrics
          </h3>
        </div>

        <div className="flex items-center gap-2 text-[10px] font-mono text-text-muted uppercase">
          <span className="w-2 h-2 rounded-full bg-good" />
          Live
        </div>
      </div>

      {/* Chart */}
      <div className="p-5">
        <div style={{ width: "100%", height: 300 }}>
          <ResponsiveContainer>
            <LineChart
              data={data}
              margin={{
                top: 10,
                right: 15,
                left: -15,
                bottom: 5,
              }}
            >
              <CartesianGrid
                stroke="#1E2A35"
                strokeDasharray="3 5"
                vertical={false}
              />

              <XAxis
                dataKey="time"
                tick={{
                  fill: "#7C8B9B",
                  fontSize: 10,
                }}
                axisLine={{
                  stroke: "#1E2A35",
                }}
                tickLine={false}
              />

              <YAxis
                tick={{
                  fill: "#7C8B9B",
                  fontSize: 10,
                }}
                axisLine={false}
                tickLine={false}
                width={40}
              />

              <Tooltip
                contentStyle={{
                  background: "#10161D",
                  border: "1px solid #1E2A35",
                  borderRadius: "8px",
                  fontSize: 12,
                  padding: "10px 12px",
                }}
                labelStyle={{
                  color: "#7C8B9B",
                  marginBottom: 4,
                }}
              />

              <Legend
                verticalAlign="bottom"
                height={30}
                wrapperStyle={{
                  fontSize: 11,
                  paddingTop: 10,
                }}
              />

              <Line
                type="monotone"
                dataKey="cpu"
                name="CPU %"
                stroke="#5FD4D0"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
                isAnimationActive={false}
              />

              <Line
                type="monotone"
                dataKey="memory"
                name="Memory %"
                stroke="#FFB454"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
                isAnimationActive={false}
              />

              <Line
                type="monotone"
                dataKey="latency"
                name="Latency (ms)"
                stroke="#FB7185"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </section>
  );
}
