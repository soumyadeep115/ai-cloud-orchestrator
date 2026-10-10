import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchClusterMetrics, fetchClusters, fetchDecisions } from "./api";
import Sidebar, { NAV } from "./components/layout/Sidebar";
import Topbar from "./components/layout/Topbar";
import { ErrorBanner } from "./components/ui/Panel";
import { MAX_REPLICAS, RANGES } from "./config";
import usePolling from "./hooks/usePolling";
import { isNum } from "./lib/format";
import { latest, normalizeMetrics, values, withWorkloadReplicas } from "./lib/metrics";
import DecisionsView from "./views/DecisionsView";
import LatencyView from "./views/LatencyView";
import OverviewView from "./views/OverviewView";
import PodsView from "./views/PodsView";
import ResourcesView from "./views/ResourcesView";
import TrafficView from "./views/TrafficView";

const VIEWS = {
  overview: OverviewView,
  pods: PodsView,
  latency: LatencyView,
  traffic: TrafficView,
  resources: ResourcesView,
  decisions: DecisionsView,
};
const TITLES = Object.fromEntries(NAV.flatMap((g) => g.items.map((i) => [i.id, i.label])));

const initialView = () => {
  const h = window.location.hash.replace("#", "");
  return h in VIEWS ? h : "overview";
};

export default function App() {
  const [view, setView] = useState(initialView);
  const [selectedId, setSelectedId] = useState(null);
  const [rangeLabel, setRangeLabel] = useState("30m");
  const [refreshMs, setRefreshMs] = useState(15000);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    window.location.hash = view;
  }, [view]);

  const limit = RANGES.find((r) => r.label === rangeLabel)?.limit ?? 120;

  const clustersFetcher = useCallback((s) => fetchClusters(s), []);
  const clustersQ = usePolling(clustersFetcher, "clusters", refreshMs);
  const clusters = useMemo(() => clustersQ.data ?? [], [clustersQ.data]);

  // pick the first *healthy* cluster once the list arrives (unreachable ones have no data)
  useEffect(() => {
    if (selectedId === null && clusters.length > 0) {
      setSelectedId((clusters.find((c) => c.status === "healthy") ?? clusters[0]).id);
    }
  }, [clusters, selectedId]);

  const metricsFetcher = useCallback((s) => fetchClusterMetrics(selectedId, limit, s), [selectedId, limit]);
  const metricsQ = usePolling(metricsFetcher, `${selectedId}-${limit}`, refreshMs, selectedId !== null);
  const baseRows = useMemo(() => normalizeMetrics(metricsQ.data?.metrics), [metricsQ.data]);

  const decisionsFetcher = useCallback((s) => fetchDecisions(selectedId, 200, s), [selectedId]);
  const decisionsQ = usePolling(decisionsFetcher, selectedId, refreshMs, selectedId !== null);

  // pod_count from the backend counts every pod in the cluster. When it exceeds the
  // scaler's limit, rebuild the real workload replica count from the decision log.
  const { rows, podSource } = useMemo(() => {
    const clusterWide = Math.max(0, ...values(baseRows, "pods")) > MAX_REPLICAS;
    if (!clusterWide) return { rows: baseRows, podSource: "metrics" };
    const rebuilt = withWorkloadReplicas(baseRows, decisionsQ.data);
    return rebuilt ? { rows: rebuilt, podSource: "decisions" } : { rows: baseRows, podSource: "clusterwide" };
  }, [baseRows, decisionsQ.data]);

  const cluster = clusters.find((c) => c.id === selectedId) ?? null;
  const podsNow = podSource === "clusterwide" ? null : latest(rows, "pods") ?? (isNum(cluster?.pod_count) && cluster.pod_count <= MAX_REPLICAS ? cluster.pod_count : null);
  const apiOk = !clustersQ.error || clustersQ.data !== null;
  const View = VIEWS[view];

  const refreshAll = () => {
    clustersQ.refresh();
    if (selectedId !== null) {
      metricsQ.refresh();
      decisionsQ.refresh();
    }
  };

  const ctx = {
    clusters,
    selectedId,
    setSelectedId,
    cluster,
    rows,
    decisions: decisionsQ.data,
    podsNow,
    podSource,
    refreshMs,
  };

  return (
    <div className="min-h-screen flex">
      <Sidebar
        view={view}
        onView={setView}
        clusters={clusters}
        selectedId={selectedId}
        onSelectCluster={setSelectedId}
        open={menuOpen}
        onClose={() => setMenuOpen(false)}
        apiOk={apiOk}
      />

      <div className="flex-1 min-w-0 flex flex-col">
        <Topbar
          title={TITLES[view]}
          clusterName={cluster?.name}
          range={rangeLabel}
          onRange={setRangeLabel}
          refreshMs={refreshMs}
          onRefreshMs={setRefreshMs}
          updatedAt={clustersQ.updatedAt}
          onRefresh={refreshAll}
          onMenu={() => setMenuOpen(true)}
        />

        <main className="px-4 sm:px-6 py-6 w-full max-w-7xl mx-auto space-y-6">
          {clustersQ.error && clustersQ.data === null && (
            <ErrorBanner>
              Couldn't reach the API ({clustersQ.error.message}). Check the backend is running and CORS allows this origin — see README.
            </ErrorBanner>
          )}
          {metricsQ.error && clustersQ.data !== null && (
            <ErrorBanner>Metrics request failed: {metricsQ.error.message}</ErrorBanner>
          )}
          {clustersQ.loading && clusters.length === 0 && !clustersQ.error && (
            <div className="text-text-muted font-mono text-sm">Loading clusters…</div>
          )}

          {(selectedId !== null || view === "overview") && clusters.length > 0 && <View ctx={ctx} />}
        </main>
      </div>
    </div>
  );
}
