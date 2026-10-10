import TimeSeriesChart, { Legend } from "../components/charts/TimeSeriesChart";
import Panel, { Empty } from "../components/ui/Panel";
import Stat, { StatGrid } from "../components/ui/Stat";
import { COLORS } from "../config";
import { fmt } from "../lib/format";
import { latest, mean, values } from "../lib/metrics";

const pctTone = (v) => (v >= 85 ? "bad" : v >= 65 ? "warn" : "good");

export default function ResourcesView({ ctx }) {
  const { rows, cluster, podsNow } = ctx;
  const cpu = cluster?.cpu_percent ?? latest(rows, "cpu");
  const mem = cluster?.memory_percent ?? latest(rows, "memory");
  const cpuVals = values(rows, "cpu");
  const memVals = values(rows, "memory");

  if (!rows.length) return <Empty>No stored metrics yet for this cluster.</Empty>;

  return (
    <div className="space-y-6">
      <StatGrid>
        <Stat label="CPU now" value={fmt(cpu, 1)} unit="%" tone={pctTone(cpu)} hint={`avg ${fmt(mean(cpuVals), 1)}% · peak ${fmt(cpuVals.length ? Math.max(...cpuVals) : null, 1)}%`} />
        <Stat label="Memory now" value={fmt(mem, 1)} unit="%" tone={pctTone(mem)} hint={`avg ${fmt(mean(memVals), 1)}% · peak ${fmt(memVals.length ? Math.max(...memVals) : null, 1)}%`} />
        <Stat label="Nodes" value={fmt(cluster?.node_count ?? latest(rows, "nodes"), 0)} />
        <Stat label="Workload pods" value={fmt(podsNow, 0)} tone="violet" />
      </StatGrid>

      <Panel title="CPU and memory" subtitle="cluster-wide utilisation">
        <TimeSeriesChart
          data={rows}
          height={280}
          leftUnit="%"
          leftDomain={[0, 100]}
          series={[
            { key: "cpu", name: "CPU", color: COLORS.cpu, kind: "line", unit: "%" },
            { key: "memory", name: "Memory", color: COLORS.memory, kind: "line", unit: "%" },
          ]}
        />
        <Legend items={[{ label: "CPU %", color: COLORS.cpu }, { label: "Memory %", color: COLORS.memory }]} />
      </Panel>

      <Panel title="CPU vs pods" subtitle="CPU per replica should fall as pods are added">
        <TimeSeriesChart
          data={rows}
          height={240}
          leftUnit="%"
          integerRight
          series={[
            { key: "cpu", name: "CPU", color: COLORS.cpu, kind: "area", unit: "%" },
            { key: "pods", name: "Pods", color: COLORS.pods, kind: "step", axis: "right" },
          ]}
        />
        <Legend items={[{ label: "CPU % (left)", color: COLORS.cpu }, { label: "Pods (right)", color: COLORS.pods }]} />
      </Panel>
    </div>
  );
}
