import { useCallback, useState } from "react";
import { fetchDecisionPreview } from "../api";
import Badge, { actionLabel, actionTone, regimeTone } from "../components/ui/Badge";
import Panel, { Empty, ErrorBanner } from "../components/ui/Panel";
import Stat, { StatGrid } from "../components/ui/Stat";
import usePolling from "../hooks/usePolling";
import { fmt, fmtTime, isNum, timeAgo } from "../lib/format";

export default function DecisionsView({ ctx }) {
  const { decisions, selectedId, refreshMs } = ctx;
  const fetcher = useCallback((signal) => fetchDecisionPreview(selectedId, signal), [selectedId]);
  // commit=false on the backend: a read-only preview, nothing is logged or actuated.
  const { data: p, error } = usePolling(fetcher, selectedId, refreshMs || 15000, selectedId !== null);

  const [scalingOnly, setScalingOnly] = useState(true);
  const shown = (decisions ?? []).filter((d) => !scalingOnly || d.action !== "no_action");

  const counts = (decisions ?? []).reduce((acc, d) => ({ ...acc, [d.action]: (acc[d.action] ?? 0) + 1 }), {});

  return (
    <div className="space-y-6">
      <Panel title="Right now" subtitle="what the orchestrator would do this cycle (read-only preview — nothing is applied; replica count is taken from the last logged decision)">
        {error && !p && <ErrorBanner>{error.message}</ErrorBanner>}
        {!p && !error && <p className="text-sm font-mono text-text-muted">Evaluating…</p>}
        {p && (
          <div className="space-y-5">
            <div className="flex flex-wrap items-center gap-3">
              <Badge tone={actionTone(p.action)}>{actionLabel(p.action)}</Badge>
              <span className="font-mono text-2xl tabular-nums">
                {p.prev_replicas} <span className="text-text-muted">→</span> {p.next_replicas}
              </span>
              <span className="text-xs font-mono text-text-muted">replicas</span>
              <span className="ml-auto flex gap-2">
                <Badge tone={regimeTone(p.regime)}>{p.regime}</Badge>
                <Badge tone="info">{String(p.source).replace("_", " ")}</Badge>
                {p.step_capped && <Badge tone="warn">step capped</Badge>}
                {p.cooldown_blocked && <Badge tone="warn">cooldown</Badge>}
              </span>
            </div>

            <div>
              <div className="flex justify-between text-[10px] uppercase tracking-wide text-text-muted mb-1.5">
                <span>Trust in the model</span>
                <span className="font-mono">{fmt((p.confidence ?? 0) * 100, 0)}%</span>
              </div>
              <div className="h-1.5 rounded bg-hairline overflow-hidden">
                <div className="h-full bg-accent transition-all" style={{ width: `${(p.confidence ?? 0) * 100}%` }} />
              </div>
            </div>

            <StatGrid>
              <Stat label="Current req/s" value={fmt(p.current_rate)} tone="good" />
              <Stat label="Predicted req/s" value={fmt(p.predicted_rate)} tone="accent" />
              <Stat label="Volatility" value={fmt(p.mean_jump, 2)} hint="mean |Δ req/s|" />
              <Stat
                label="Target pods"
                value={`${fmt(p.reactive_target, 0)} / ${fmt(p.model_target, 0)} / ${fmt(p.blended_target, 0)}`}
                hint="reactive / model / blended"
                tone="violet"
              />
            </StatGrid>

            <p className="text-sm text-text-muted font-mono leading-relaxed border-l-2 border-hairline pl-3">{p.reason}</p>
          </div>
        )}
      </Panel>

      <StatGrid>
        <Stat label="Decisions logged" value={decisions?.length ?? "—"} hint="most recent 200 (one per 15s cycle)" />
        <Stat label="Scale ups" value={counts.scale_up ?? 0} tone="good" />
        <Stat label="Scale downs" value={counts.scale_down ?? 0} tone="bad" />
        <Stat label="Holds" value={counts.no_action ?? 0} />
      </StatGrid>

      <Panel
        title="Decision history"
        subtitle="newest first — logged by the decision loop"
        right={
          <label className="flex items-center gap-2 text-[11px] font-mono text-text-muted cursor-pointer select-none">
            <input type="checkbox" checked={scalingOnly} onChange={(e) => setScalingOnly(e.target.checked)} className="accent-accent" />
            scaling only
          </label>
        }
      >
        {!decisions?.length ? (
          <Empty>No decisions logged for this cluster yet. Start the loop: python -m app.orchestration.loop</Empty>
        ) : shown.length === 0 ? (
          <p className="text-sm text-text-muted font-mono">Only holds in the last {decisions.length} decisions — untick "scaling only" to see them.</p>
        ) : (
          <div className="overflow-x-auto -mx-1">
            <table className="w-full text-left text-xs font-mono">
              <thead>
                <tr className="text-[10px] uppercase tracking-wide text-text-muted border-b border-hairline">
                  <th className="py-2 px-1 font-normal">Time</th>
                  <th className="py-2 px-1 font-normal">Action</th>
                  <th className="py-2 px-1 font-normal">Pods</th>
                  <th className="py-2 px-1 font-normal">Source</th>
                  <th className="py-2 px-1 font-normal">Predicted</th>
                  <th className="py-2 px-1 font-normal">Conf.</th>
                  <th className="py-2 px-1 font-normal min-w-64">Reasoning</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline">
                {shown.map((d, i) => (
                  <tr key={`${d.ts}-${i}`} className="align-top">
                    <td className="py-2 px-1 whitespace-nowrap">
                      {fmtTime(d.ts)}
                      <div className="text-[10px] text-text-muted">{timeAgo(d.ts)}</div>
                    </td>
                    <td className="py-2 px-1">
                      <Badge tone={actionTone(d.action)}>{actionLabel(d.action)}</Badge>
                    </td>
                    <td className="py-2 px-1 tabular-nums whitespace-nowrap">
                      {d.prev_pods} → {d.next_pods}
                    </td>
                    <td className="py-2 px-1">{d.source === "ml" ? "ML" : "threshold"}</td>
                    <td className="py-2 px-1 tabular-nums">{isNum(d.predicted_value) ? fmt(d.predicted_value) : "—"}</td>
                    <td className="py-2 px-1 tabular-nums">{isNum(d.confidence) ? fmt(d.confidence, 2) : "—"}</td>
                    <td className="py-2 px-1 text-text-muted leading-relaxed">{d.reasoning}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}
