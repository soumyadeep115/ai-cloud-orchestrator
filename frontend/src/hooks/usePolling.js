import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Poll an async fetcher.
 *  - fetcher(signal) -> Promise
 *  - resetKey: when it changes (e.g. selected cluster) old data is dropped
 *  - intervalMs: 0 disables auto-refresh (manual refresh() still works)
 *  - enabled: false pauses polling entirely (e.g. view not on screen)
 */
export default function usePolling(fetcher, resetKey, intervalMs, enabled = true) {
  const [state, setState] = useState({ data: null, error: null, loading: true, updatedAt: null });
  const abortRef = useRef(null);
  const fetcherRef = useRef(fetcher);

  useEffect(() => {
    fetcherRef.current = fetcher;
  });

  const run = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const data = await fetcherRef.current(controller.signal);
      if (controller.signal.aborted) return;
      setState({ data, error: null, loading: false, updatedAt: new Date() });
    } catch (e) {
      if (controller.signal.aborted && e.name === "AbortError") return;
      setState((s) => ({ ...s, error: e, loading: false }));
    }
  }, []);

  useEffect(() => {
    if (!enabled) return undefined;
    setState({ data: null, error: null, loading: true, updatedAt: null });
    run();
    const id = intervalMs > 0 ? setInterval(run, intervalMs) : null;
    return () => {
      if (id) clearInterval(id);
      abortRef.current?.abort();
    };
  }, [enabled, intervalMs, resetKey, run]);

  return { ...state, refresh: run };
}
