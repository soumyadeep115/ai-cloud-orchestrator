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

      setSelectedId((prev) =>
        prev === null && data.length > 0 ? data[0].id : prev
      );
    } catch (e) {
      if (e.name !== "AbortError") {
        setError(e.message);
      }
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
        const data = await fetchClusterMetrics(
          selectedId,
          60,
          controller.signal
        );

        setMetricsData(data);
      } catch (e) {
        if (e.name !== "AbortError") {
          setError(e.message);
        }
      }
    };

    load();

    const id = setInterval(load, POLL_MS);

    return () => {
      clearInterval(id);
      metricsAbortRef.current?.abort();
    };
  }, [selectedId]);

  const systemOnline = !error;

  return (
    <div className="min-h-screen">
      {/* Top navigation */}
      <header className="border-b border-hairline bg-panel/70 backdrop-blur">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-9 h-9 rounded-lg border border-accent/30 bg-accent/10">
              <span className="text-accent text-lg">◆</span>
            </div>

            <div>
              <h1 className="font-display font-semibold text-base text-text-primary">
                AI Cloud Orchestrator
              </h1>

              <p className="text-[10px] text-text-muted font-mono uppercase tracking-wider">
                Infrastructure control plane
              </p>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <div className="hidden sm:block text-right">
              <div className="text-[9px] text-text-muted font-mono uppercase tracking-wider">
                Last synchronization
              </div>

              <div className="text-xs font-mono text-text-primary">
                {lastUpdated
                  ? lastUpdated.toLocaleTimeString()
                  : "Connecting..."}
              </div>
            </div>

            <div
              className={`flex items-center gap-2 rounded-full border px-3 py-1.5 text-[10px] font-mono uppercase tracking-wide ${
                systemOnline
                  ? "border-good/30 bg-good/10 text-good"
                  : "border-bad/30 bg-bad/10 text-bad"
              }`}
            >
              <span
                className={`w-2 h-2 rounded-full ${
                  systemOnline ? "bg-good" : "bg-bad"
                }`}
              />

              {systemOnline ? "System online" : "System offline"}
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-8 space-y-8">
        {/* Dashboard heading */}
        <section>
          <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
            <div>
              <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-accent mb-2">
                Overview
              </div>

              <h2 className="font-display text-3xl font-semibold tracking-tight text-text-primary">
                Cluster dashboard
              </h2>

              <p className="mt-2 text-sm text-text-muted max-w-xl">
                Monitor infrastructure health, resource utilization, and
                cluster performance in real time.
              </p>
            </div>

            <div className="text-xs font-mono text-text-muted">
              {clusters.length}{" "}
              {clusters.length === 1 ? "cluster" : "clusters"} detected
            </div>
          </div>
        </section>

        {/* Error */}
        {error && (
          <div className="rounded-xl border border-bad/30 bg-bad/10 p-4">
            <div className="flex items-start gap-3">
              <span className="mt-0.5 w-2 h-2 rounded-full bg-bad shrink-0" />

              <div>
                <div className="text-xs font-mono uppercase tracking-wider text-bad mb-1">
                  Connection error
                </div>

                <p className="text-sm text-bad/90 font-mono leading-relaxed">
                  Couldn't reach the API at the configured URL ({error}).
                  Check that the backend is running and CORS is enabled.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Loading */}
        {!error && clusters.length === 0 && (
          <div className="rounded-xl border border-hairline bg-panel p-8 text-center">
            <div className="mx-auto mb-3 w-3 h-3 rounded-full bg-accent animate-pulse" />

            <div className="text-xs font-mono uppercase tracking-wider text-text-muted">
              Loading clusters...
            </div>

            <p className="mt-2 text-xs text-text-muted">
              Connecting to the orchestration API
            </p>
          </div>
        )}

        {/* Cluster cards */}
        {clusters.length > 0 && (
          <section>
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="font-display font-semibold text-lg text-text-primary">
                  Your clusters
                </h3>

                <p className="text-xs text-text-muted mt-1">
                  Select a cluster to inspect its performance metrics.
                </p>
              </div>

              <div className="hidden sm:flex items-center gap-2 text-[10px] font-mono text-text-muted uppercase">
                <span className="w-2 h-2 rounded-full bg-good" />
                Healthy
              </div>
            </div>

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
          </section>
        )}

        {/* Metrics */}
        {selectedId !== null && (
          <section>
            <div className="mb-4">
              <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-accent mb-1">
                Analytics
              </div>

              <h3 className="font-display font-semibold text-lg text-text-primary">
                Performance metrics
              </h3>
            </div>

            <MetricsChart
              clusterName={metricsData?.cluster_name}
              metrics={metricsData?.metrics}
            />
          </section>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-hairline mt-8">
        <div className="max-w-6xl mx-auto px-6 py-5 flex flex-col sm:flex-row items-center justify-between gap-2">
          <span className="text-[10px] font-mono text-text-muted uppercase tracking-wider">
            AI Cloud Orchestrator
          </span>

          <span className="text-[10px] font-mono text-text-muted">
            Automatic refresh every 30s
          </span>
        </div>
      </footer>
    </div>
  );
}
