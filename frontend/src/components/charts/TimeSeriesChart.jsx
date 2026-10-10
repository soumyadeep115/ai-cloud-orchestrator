import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { COLORS } from "../../config";
import { fmtClock, fmtTime, isNum } from "../../lib/format";

/**
 * series: [{ key, name, color, kind: 'line'|'area'|'step', axis: 'left'|'right', unit, dashed }]
 * markers: [{ t, color, label }]   vertical event lines
 * refLines: [{ y, color, label, axis }] horizontal threshold lines
 */
export default function TimeSeriesChart({
  data,
  series,
  height = 260,
  markers = [],
  refLines = [],
  leftUnit = "",
  rightUnit = "",
  leftDomain = [0, "auto"],
  rightDomain = [0, "auto"],
  xDomain,
  integerLeft = false,
  integerRight = false,
}) {
  const hasRight = series.some((s) => s.axis === "right");
  const axisProps = { tick: { fill: COLORS.axis, fontSize: 11 }, axisLine: false, tickLine: false };

  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer>
        <ComposedChart data={data} margin={{ top: 6, right: hasRight ? 0 : 8, left: -8, bottom: 0 }}>
          <CartesianGrid stroke={COLORS.grid} strokeDasharray="3 5" vertical={false} />
          <XAxis
            dataKey="t"
            type="number"
            scale="time"
            domain={xDomain ?? ["dataMin", "dataMax"]}
            tickFormatter={fmtClock}
            tick={{ fill: COLORS.axis, fontSize: 11 }}
            axisLine={{ stroke: COLORS.grid }}
            tickLine={false}
            minTickGap={48}
          />
          <YAxis
            yAxisId="left"
            width={46}
            domain={leftDomain}
            allowDecimals={!integerLeft}
            tickFormatter={(v) => `${v}${leftUnit}`}
            {...axisProps}
          />
          {hasRight && (
            <YAxis
              yAxisId="right"
              orientation="right"
              width={46}
              domain={rightDomain}
              allowDecimals={!integerRight}
              tickFormatter={(v) => `${v}${rightUnit}`}
              {...axisProps}
            />
          )}
          <Tooltip content={<ChartTooltip series={series} />} cursor={{ stroke: COLORS.axis, strokeDasharray: "3 3" }} />

          {refLines.map((r) => (
            <ReferenceLine
              key={`${r.label}-${r.y}`}
              yAxisId={r.axis ?? "left"}
              y={r.y}
              stroke={r.color}
              strokeDasharray="5 4"
              strokeOpacity={0.7}
              label={{ value: r.label, fill: r.color, fontSize: 10, position: "insideTopRight" }}
            />
          ))}
          {markers.map((m) => (
            <ReferenceLine
              key={`${m.t}-${m.label}`}
              yAxisId="left"
              x={m.t}
              stroke={m.color}
              strokeOpacity={0.55}
              strokeDasharray="2 3"
            />
          ))}

          {series.map((s) => {
            const common = {
              yAxisId: s.axis ?? "left",
              dataKey: s.key,
              name: s.name,
              stroke: s.color,
              strokeWidth: 2,
              strokeDasharray: s.dashed ? "6 4" : undefined,
              isAnimationActive: false,
              connectNulls: !!s.connectNulls,
            };
            if (s.kind === "area" || s.kind === "step") {
              return (
                <Area
                  key={s.key}
                  {...common}
                  type={s.kind === "step" ? "stepAfter" : "monotone"}
                  fill={s.color}
                  fillOpacity={0.12}
                  dot={false}
                />
              );
            }
            return <Line key={s.key} {...common} type="monotone" dot={s.dot ?? false} />;
          })}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

function ChartTooltip({ active, payload, label, series }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border border-hairline bg-panel px-3 py-2 text-xs font-mono shadow-lg">
      <div className="text-text-muted mb-1">{fmtTime(label)}</div>
      {payload
        .filter((p) => isNum(p.value))
        .map((p) => {
          const unit = series.find((s) => s.key === p.dataKey)?.unit ?? "";
          return (
            <div key={p.dataKey} className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full" style={{ background: p.color }} />
              <span className="text-text-muted">{p.name}</span>
              <span className="ml-auto pl-4 tabular-nums text-text-primary">
                {Math.round(p.value * 10) / 10}
                {unit}
              </span>
            </div>
          );
        })}
    </div>
  );
}

export function Legend({ items }) {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 mt-3 text-[11px] font-mono text-text-muted">
      {items.map((i) => (
        <span key={i.label} className="flex items-center gap-1.5">
          <span className="w-2.5 h-0.5 rounded" style={{ background: i.color }} />
          {i.label}
        </span>
      ))}
    </div>
  );
}
