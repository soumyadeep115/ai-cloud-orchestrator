import { useMemo } from "react";
import TimeSeriesChart from "../components/charts/TimeSeriesChart";
import Badge from "../components/ui/Badge";
import Panel, { Empty } from "../components/ui/Panel";
import PodGrid from "../components/ui/PodGrid";
import Stat, { StatGrid } from "../components/ui/Stat";
import { COLORS, LIVE_MAX_REPLICAS, MAX_REPLICAS, MIN_REPLICAS, SCALE_DOWN_UTIL, SCALE_UP_UTIL } from "../config";
import { fmt, fmtTime, timeAgo } from "../lib/format";
import { podChanges, values } from "../lib/metrics";

export default function PodsView({ ctx }) {
  const { rows, podsNow, podSource } = ctx;
  const changes = useMemo(() => podChanges(rows), [rows]);
  const pods = values(rows, "pods");
  const ups = changes.filter((c) => c.dir === "up").length;
  const downs = changes.length - ups;
  const last = changes[changes.length - 1];
  const markers = changes.map((c) => ({ t: c.t, label: `${c.from}→${c.to}`, color: c.dir === "up" ? COLORS.up : COLORS.down }));
  const clusterWide = podSource === "clusterwide";

  if (!rows.length) return <Empty>No stored metrics yet for this cluster.</Empty>;

  return (
    <div className="space-y-6">
      {podSource === "decisions" && (
        <div className="rounded-lg border border-info/30 bg-info/10 text-info text-xs font-mono p-3 leading-relaxed">
          Replica counts are rebuilt from the decision log (the stored pod_count includes every pod in the cluster). History only goes back
          as far as the last 200 logged decisions (about 50 minutes). To store the true count, change the pod_count query — see README, "Pod count".
        </div>
      )}
      {clusterWide && (
        <div className="rounded-lg border border-warn/40 bg-warn/10 text-warn text-xs font-mono p-3 leading-relaxed">
          The stored pod_count counts every pod in the cluster (system pods included) and there is no decision history to correct it, so
          replica data is hidden. Start the decision loop (python -m app.orchestration.loop) or fix the pod_count query — see README, "Pod count".
        </div>
      )}

      <StatGrid>
        <Stat label="Replicas now" value={fmt(podsNow, 0)} tone="violet" hint={`min ${MIN_REPLICAS} · live cap ${LIVE_MAX_REPLICAS} · limit ${MAX_REPLICAS}`} />
        <Stat label="Peak / low in range" value={pods.length && !clusterWide ? `${Math.max(...pods)} / ${Math.min(...pods)}` : "—"} hint="replicas" />
        <Stat label="Scale events" value={clusterWide ? "—" : `${ups} ↑  ${downs} ↓`} hint="observed in range" />
        <Stat
          label="Last change"
          value={last && !clusterWide ? `${last.from} → ${last.to}` : "none"}
          hint={last && !clusterWide ? timeAgo(last.t) : "stable throughout range"}
          tone={last && !clusterWide ? (last.dir === "up" ? "good" : "bad") : "default"}
        />
      </StatGrid>

      <Panel title="Replicas over time" subtitle="green line = scale up, red line = scale down">
        <TimeSeriesChart
          data={rows}
          height={280}
          integerLeft
          leftDomain={clusterWide ? ["auto", "auto"] : [0, MAX_REPLICAS]}
          markers={clusterWide ? [] : markers}
          refLines={
            clusterWide
              ? []
              : [
                  { y: MAX_REPLICAS, color: COLORS.nodes, label: `limit ${MAX_REPLICAS}` },
                  { y: LIVE_MAX_REPLICAS, color: COLORS.down, label: `live cap ${LIVE_MAX_REPLICAS}` },
                  { y: MIN_REPLICAS, color: COLORS.nodes, label: `min ${MIN_REPLICAS}` },
                ]
          }
          series={[{ key: "pods", name: "Replicas", color: COLORS.pods, kind: "step" }]}
        />
      </Panel>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <Panel title="Current replicas" className="xl:col-span-1">
          <PodGrid pods={podsNow} />
        </Panel>

        <Panel
          title="Estimated utilisation"
          subtitle={`req/s ÷ (replicas × capacity). Orchestrator scales up above ${SCALE_UP_UTIL * 100}%, down below ${SCALE_DOWN_UTIL * 100}%`}
          className="xl:col-span-2"
        >
          <TimeSeriesChart
            data={rows}
            height={220}
            leftUnit="%"
            leftDomain={[0, (max) => Math.max(100, Math.ceil(max / 10) * 10)]}
            refLines={[
              { y: SCALE_UP_UTIL * 100, color: COLORS.up, label: "scale up" },
              { y: SCALE_DOWN_UTIL * 100, color: COLORS.down, label: "scale down" },
            ]}
            series={[{ key: "util", name: "Utilisation", color: COLORS.memory, kind: "area", unit: "%" }]}
          />
        </Panel>
      </div>

      <Panel title="Replica change log" subtitle="changes in the replica count (newest first)">
        {changes.length === 0 || clusterWide ? (
          <p className="text-sm text-text-muted font-mono">No replica changes in this time range.</p>
        ) : (
          <ul className="divide-y divide-hairline">
            {[...changes].reverse().map((c) => (
              <li key={c.t} className="py-2.5 flex items-center gap-3 text-sm">
                <Badge tone={c.dir === "up" ? "good" : "bad"}>{c.dir === "up" ? "scale up" : "scale down"}</Badge>
                <span className="font-mono tabular-nums">
                  {c.from} → {c.to} replicas
                </span>
                <span className="ml-auto font-mono text-[11px] text-text-muted">
                  {fmtTime(c.t)} · {timeAgo(c.t)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}
