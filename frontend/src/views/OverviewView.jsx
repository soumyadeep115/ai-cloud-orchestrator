import ClusterCard from "../components/ui/ClusterCard";
import TimeSeriesChart, { Legend } from "../components/charts/TimeSeriesChart";
import Panel, { Empty } from "../components/ui/Panel";
import PodGrid from "../components/ui/PodGrid";
import Stat, { StatGrid } from "../components/ui/Stat";
import Badge, { actionLabel, actionTone } from "../components/ui/Badge";
import { COLORS } from "../config";
import { fmt, fmtMs, timeAgo } from "../lib/format";

export default function OverviewView({ ctx }) {
  const { clusters, selectedId, setSelectedId, cluster, rows, decisions, podsNow } = ctx;
  const lastDecision = decisions?.[0];

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {clusters.map((c) => (
          <ClusterCard key={c.id} cluster={c} selected={c.id === selectedId} onClick={() => setSelectedId(c.id)} />
        ))}
      </div>

      {cluster && (
        <>
          <StatGrid>
            <Stat label="Pods running" value={fmt(podsNow, 0)} tone="violet" hint={`${fmt(cluster.node_count, 0)} node(s)`} />
            <Stat label="Latency p99" value={fmtMs(cluster.latency_ms)} tone="bad" />
            <Stat label="Requests / s" value={fmt(cluster.request_rate)} tone="good" />
            <Stat label="CPU / Memory" value={`${fmt(cluster.cpu_percent, 0)} / ${fmt(cluster.memory_percent, 0)}`} unit="%" tone="accent" />
          </StatGrid>

          <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
            <Panel title="Replicas" subtitle="demo-workload replicas" className="xl:col-span-1">
              <PodGrid pods={podsNow} desired={lastDecision?.next_pods} />
              {lastDecision && (
                <div className="mt-5 pt-4 border-t border-hairline">
                  <div className="text-[10px] uppercase tracking-wide text-text-muted mb-2">Last orchestrator decision</div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <Badge tone={actionTone(lastDecision.action)}>{actionLabel(lastDecision.action)}</Badge>
                    <span className="font-mono text-sm">
                      {lastDecision.prev_pods} → {lastDecision.next_pods}
                    </span>
                    <span className="text-[11px] font-mono text-text-muted">{timeAgo(lastDecision.ts)}</span>
                  </div>
                </div>
              )}
            </Panel>

            <Panel title="Pods vs request rate" subtitle="scaling follows load" className="xl:col-span-2">
              {rows.length ? (
                <>
                  <TimeSeriesChart
                    data={rows}
                    height={220}
                    integerLeft
                    series={[
                      { key: "pods", name: "Pods", color: COLORS.pods, kind: "step" },
                      { key: "rate", name: "Req/s", color: COLORS.rate, kind: "line", axis: "right" },
                    ]}
                  />
                  <Legend items={[{ label: "Pods (left)", color: COLORS.pods }, { label: "Req/s (right)", color: COLORS.rate }]} />
                </>
              ) : (
                <Empty>No stored metrics yet — the poller writes a row every 15s.</Empty>
              )}
            </Panel>
          </div>

          <Panel title="Latency p99" subtitle="over the selected range">
            {rows.length ? (
              <TimeSeriesChart
                data={rows}
                height={200}
                leftUnit="ms"
                series={[{ key: "latency", name: "p99 latency", color: COLORS.latency, kind: "area", unit: " ms" }]}
              />
            ) : (
              <Empty>No latency samples yet.</Empty>
            )}
          </Panel>
        </>
      )}
    </div>
  );
}
