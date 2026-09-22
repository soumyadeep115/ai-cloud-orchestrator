import { useEffect, useState, useCallback, useRef } from "react";
import { fetchClusters, fetchClusterMetrics } from "./api";
import ClusterCard from "./components/ClusterCard";
import MetricsChart from "./components/MetricsChart";

const POLL_MS = 30000;

export default function App() {
  const [clusters, setClusters] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [metricsData, setMetricsData] = useState(null);
  const [error, setError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);

  // one AbortController per in-flight request type, so a new poll can
  // always cancel whatever's still pending from the previous one
  const clustersAbortRef = useRef(null);
  const metricsAbortRef = useRef(null);

  const loadClusters = useCallback(async () => {
    clustersAbortRef.current?.abort();
    const controller = new AbortController();
    clustersAbortRef.current = controller;

    try {
      const data = await fetchClusters(controller.signal);
      setClusters(data);
      setError(null);
      setLastUpdated(new Date());
      setSelectedId((prev) => (prev === null && data.length > 0 ? data[0].id : prev));
    } catch (e) {
      if (e.name !== "AbortError") setError(e.message);
    }
  }, []);

  useEffect(() => {
    loadClusters();
    const id = setInterval(loadClusters, POLL_MS);
    return () => {
      clearInterval(id);
      clustersAbortRef.current?.abort();
    };
  }, [loadClusters]);

  useEffect(() => {
    if (selectedId === null) return;

    const load = async () => {
      metricsAbortRef.current?.abort();
      const controller = new AbortController();
      metricsAbortRef.current = controller;
      try {
        const data = await fetchClusterMetrics(selectedId, 60, controller.signal);
        setMetricsData(data);
      } catch (e) {
        if (e.name !== "AbortError") setError(e.message);
      }
    };

    load();
    const id = setInterval(load, POLL_MS);
    return () => {
      clearInterval(id);
      metricsAbortRef.current?.abort();
    };
  }, [selectedId]);

  return (
    <div className="min-h-screen">
      <header className="border-b border-hairline px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="font-display font-semibold text-lg">Orchestrator.control</h1>
          <p className="text-[11px] text-text-muted font-mono">live cluster monitoring — Phase 1</p>
        </div>
        <div className="text-xs font-mono text-text-muted">
          {lastUpdated ? `updated ${lastUpdated.toLocaleTimeString()}` : "connecting…"}
        </div>
      </header>

      <main className="px-6 py-6 max-w-5xl mx-auto space-y-6">
        {error && (
          <div className="rounded-lg border border-bad/40 bg-bad/10 text-bad text-sm font-mono p-4">
            Couldn't reach the API at the configured URL ({error}). Check the backend is running and CORS is enabled — see README.
          </div>
        )}

        {!error && clusters.length === 0 && (
          <div className="text-text-muted font-mono text-sm">Loading clusters…</div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {clusters.map((c) => (
            <ClusterCard
              key={c.id}
              cluster={c}
              selected={c.id === selectedId}
              onClick={() => setSelectedId(c.id)}
            />
          ))}
        </div>

        {selectedId !== null && (
          <MetricsChart
            clusterName={metricsData?.cluster_name}
            metrics={metricsData?.metrics}
          />
        )}
      </main>
    </div>
  );
}