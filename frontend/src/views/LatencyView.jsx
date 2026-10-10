import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import TimeSeriesChart, { Legend } from "../components/charts/TimeSeriesChart";
import Panel, { Empty } from "../components/ui/Panel";
import Stat, { StatGrid } from "../components/ui/Stat";
import { COLORS, DEFAULT_SLO_MS } from "../config";
import { fmtMs } from "../lib/format";
import { histogram, latest, mean, percentile, podChanges, values } from "../lib/metrics";

function loadSlo() {
  try {
    const v = Number(localStorage.getItem("slo_ms"));
    return v > 0 ? v : DEFAULT_SLO_MS;
  } catch {
    return DEFAULT_SLO_MS;
  }
}

export default function LatencyView({ ctx }) {
  const { rows, cluster } = ctx;
  const [slo, setSlo] = useState(loadSlo);

  const lat = useMemo(() => values(rows, "latency"), [rows]);
  const breaches = lat.filter((v) => v > slo).length;
  const breachPct = lat.length ? (breaches / lat.length) * 100 : null;
  const current = cluster?.latency_ms ?? latest(rows, "latency");
  const bins = useMemo(() => histogram(lat), [lat]);
  const markers = useMemo(
    () => podChanges(rows).map((c) => ({ t: c.t, label: `${c.from}→${c.to}`, color: c.dir === "up" ? COLORS.up : COLORS.down })),
    [rows],
  );

  const updateSlo = (e) => {
    const v = Number(e.target.value);
    setSlo(v);
    try {
      if (v > 0) localStorage.setItem("slo_ms", String(v));
    } catch {
      /* storage unavailable */
    }
  };

  if (!rows.length) return <Empty>No stored metrics yet for this cluster.</Empty>;

  return (
    <div className="space-y-6">
      <StatGrid>
        <Stat label="p99 now" value={fmtMs(current)} tone={current > slo ? "bad" : "good"} hint={`objective ${slo} ms`} />
        <Stat label="Average" value={fmtMs(mean(lat))} hint="over range" />
        <Stat label="p95 / max" value={`${fmtMs(percentile(lat, 0.95))} / ${fmtMs(lat.length ? Math.max(...lat) : null)}`} hint="of p99 samples" />
        <Stat
          label="Objective breaches"
          value={breachPct === null ? "—" : `${Math.round(breachPct)}%`}
          tone={breachPct > 10 ? "bad" : breachPct > 0 ? "warn" : "good"}
          hint={`${breaches} of ${lat.length} samples > ${slo} ms`}
        />
      </StatGrid>

      <Panel
        title="p99 latency"
        subtitle="dotted verticals mark pod scale-ups (green) and scale-downs (red)"
        right={
          <label className="flex items-center gap-2 text-[11px] font-mono text-text-muted">
            objective
            <input
              type="number"
              min="1"
              value={slo}
              onChange={updateSlo}
              className="w-20 rounded border border-hairline bg-void px-2 py-1 text-text-primary tabular-nums"
            />
            ms
          </label>
        }
      >
        <TimeSeriesChart
          data={rows}
          height={280}
          leftUnit="ms"
          markers={markers}
          refLines={[{ y: slo, color: COLORS.memory, label: `objective ${slo}ms` }]}
          series={[{ key: "latency", name: "p99 latency", color: COLORS.latency, kind: "area", unit: " ms" }]}
        />
      </Panel>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <Panel title="Latency vs pods" subtitle="does adding replicas actually bring latency down?">
          <TimeSeriesChart
            data={rows}
            height={240}
            leftUnit="ms"
            integerRight
            series={[
              { key: "latency", name: "p99 latency", color: COLORS.latency, kind: "line", unit: " ms" },
              { key: "pods", name: "Pods", color: COLORS.pods, kind: "step", axis: "right" },
            ]}
          />
          <Legend items={[{ label: "Latency (left)", color: COLORS.latency }, { label: "Pods (right)", color: COLORS.pods }]} />
        </Panel>

        <Panel title="Latency vs request rate" subtitle="load-driven latency">
          <TimeSeriesChart
            data={rows}
            height={240}
            leftUnit="ms"
            series={[
              { key: "latency", name: "p99 latency", color: COLORS.latency, kind: "line", unit: " ms" },
              { key: "rate", name: "Req/s", color: COLORS.rate, kind: "line", axis: "right" },
            ]}
          />
          <Legend items={[{ label: "Latency (left)", color: COLORS.latency }, { label: "Req/s (right)", color: COLORS.rate }]} />
        </Panel>
      </div>

      <Panel title="Latency distribution" subtitle="how many samples fell in each latency band (ms)">
        {bins.length ? (
          <div style={{ width: "100%", height: 200 }}>
            <ResponsiveContainer>
              <BarChart data={bins} margin={{ top: 4, right: 8, left: -12, bottom: 0 }}>
                <CartesianGrid stroke={COLORS.grid} strokeDasharray="3 5" vertical={false} />
                <XAxis dataKey="label" tick={{ fill: COLORS.axis, fontSize: 11 }} axisLine={{ stroke: COLORS.grid }} tickLine={false} />
                <YAxis allowDecimals={false} tick={{ fill: COLORS.axis, fontSize: 11 }} axisLine={false} tickLine={false} width={40} />
                <Tooltip
                  cursor={{ fill: "#ffffff08" }}
                  contentStyle={{ background: "#10161D", border: "1px solid #1E2A35", fontSize: 12, fontFamily: "IBM Plex Mono" }}
                  formatter={(v) => [v, "samples"]}
                  labelFormatter={(l) => `from ${l} ms`}
                />
                <Bar dataKey="count" fill={COLORS.latency} fillOpacity={0.8} radius={[3, 3, 0, 0]} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <p className="text-sm text-text-muted font-mono">Not enough latency samples yet.</p>
        )}
      </Panel>
    </div>
  );
}
