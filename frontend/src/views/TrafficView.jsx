import { useCallback, useMemo } from "react";
import { fetchPrediction } from "../api";
import TimeSeriesChart, { Legend } from "../components/charts/TimeSeriesChart";
import Panel, { Empty } from "../components/ui/Panel";
import Stat, { StatGrid } from "../components/ui/Stat";
import { COLORS, FORECAST_HORIZON_S, LIVE_MAX_REPLICAS, REQ_PER_REPLICA, SCALE_UP_UTIL } from "../config";
import usePolling from "../hooks/usePolling";
import { fmt, isNum } from "../lib/format";
import { latest, mean, values } from "../lib/metrics";

// /predict logs a row to the predictions table on every call, so poll it
// slower than the metrics (60s) rather than on the global refresh interval.
const PREDICT_MS = 60000;

export default function TrafficView({ ctx }) {
  const { rows, cluster, selectedId } = ctx;
  const fetcher = useCallback((signal) => fetchPrediction(selectedId, signal), [selectedId]);
  const { data: pred, error: predError } = usePolling(fetcher, selectedId, PREDICT_MS, selectedId !== null);

  const rates = values(rows, "rate");
  const now = cluster?.request_rate ?? latest(rows, "rate");
  const predicted = pred?.predicted_request_rate;
  const lastRow = rows[rows.length - 1];

  // Append one forecast point FORECAST_HORIZON_S after the newest sample,
  // joined to the last real value so the dashed line starts from "now".
  const chartData = useMemo(() => {
    if (!lastRow) return [];
    const base = rows.map((r) => ({ ...r, predicted: null }));
    if (isNum(predicted)) {
      base[base.length - 1] = { ...base[base.length - 1], predicted: isNum(lastRow.rate) ? lastRow.rate : predicted };
      base.push({ t: lastRow.t + FORECAST_HORIZON_S * 1000, predicted });
    }
    return base;
  }, [rows, lastRow, predicted]);

  const delta = isNum(predicted) && isNum(now) ? predicted - now : null;
  const podsNeeded = isNum(predicted) ? Math.ceil(predicted / (REQ_PER_REPLICA * SCALE_UP_UTIL)) : null;

  if (!rows.length) return <Empty>No stored metrics yet for this cluster.</Empty>;

  return (
    <div className="space-y-6">
      <StatGrid>
        <Stat label="Requests / s now" value={fmt(now)} tone="good" />
        <Stat
          label={`Forecast +${FORECAST_HORIZON_S}s`}
          value={fmt(predicted)}
          tone="accent"
          hint={isNum(delta) ? `${delta >= 0 ? "+" : ""}${fmt(delta)} vs now` : predError ? "unavailable" : "calculating…"}
        />
        <Stat label="Average / peak" value={`${fmt(mean(rates))} / ${fmt(rates.length ? Math.max(...rates) : null)}`} hint="req/s over range" />
        <Stat label="Pods to stay < 80%" value={fmt(podsNeeded, 0)} hint={podsNeeded > LIVE_MAX_REPLICAS ? `above live cap (${LIVE_MAX_REPLICAS})` : `at ${REQ_PER_REPLICA} req/s per pod`} tone={podsNeeded > LIVE_MAX_REPLICAS ? "warn" : "violet"} />
      </StatGrid>

      <Panel
        title="Request rate and forecast"
        subtitle={`dashed blue = model forecast ${FORECAST_HORIZON_S}s ahead (${pred?.model ?? "model"})`}
      >
        <TimeSeriesChart
          data={chartData}
          height={300}
          series={[
            { key: "rate", name: "Req/s", color: COLORS.rate, kind: "area" },
            { key: "predicted", name: "Forecast", color: COLORS.predicted, kind: "line", dashed: true, dot: true, connectNulls: true },
          ]}
        />
        <Legend items={[{ label: "Actual req/s", color: COLORS.rate }, { label: "Forecast", color: COLORS.predicted }]} />
        {predError && (
          <p className="mt-3 text-xs font-mono text-warn">Forecast unavailable: {predError.message}</p>
        )}
      </Panel>

      <Panel title="Traffic vs pods" subtitle="capacity should track load">
        <TimeSeriesChart
          data={rows}
          height={240}
          integerRight
          series={[
            { key: "rate", name: "Req/s", color: COLORS.rate, kind: "line" },
            { key: "pods", name: "Pods", color: COLORS.pods, kind: "step", axis: "right" },
          ]}
        />
        <Legend items={[{ label: "Req/s (left)", color: COLORS.rate }, { label: "Pods (right)", color: COLORS.pods }]} />
      </Panel>
    </div>
  );
}
