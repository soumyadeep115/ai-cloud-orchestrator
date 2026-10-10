const TONES = {
  default: "text-text-primary",
  good: "text-good",
  bad: "text-bad",
  warn: "text-warn",
  accent: "text-accent",
  violet: "text-violet",
};

export default function Stat({ label, value, unit, hint, tone = "default" }) {
  return (
    <div className="rounded-lg border border-hairline bg-panel p-4">
      <div className="text-[10px] text-text-muted uppercase tracking-wide">{label}</div>
      <div className={`mt-1.5 font-mono text-2xl font-medium tabular-nums ${TONES[tone]}`}>
        {value}
        {unit && value !== "—" && <span className="text-sm text-text-muted ml-1">{unit}</span>}
      </div>
      {hint && <div className="mt-1 text-[11px] text-text-muted font-mono">{hint}</div>}
    </div>
  );
}

export function StatGrid({ children }) {
  return <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">{children}</div>;
}
