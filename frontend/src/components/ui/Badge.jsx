const STYLES = {
  good: "text-good border-good/30 bg-good/10",
  bad: "text-bad border-bad/30 bg-bad/10",
  warn: "text-warn border-warn/30 bg-warn/10",
  info: "text-info border-info/30 bg-info/10",
  violet: "text-violet border-violet/30 bg-violet/10",
  muted: "text-text-muted border-hairline bg-panel-2",
};

export default function Badge({ tone = "muted", children }) {
  return (
    <span className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-mono uppercase tracking-wide ${STYLES[tone]}`}>
      {children}
    </span>
  );
}

export const actionTone = (a) => (a === "scale_up" ? "good" : a === "scale_down" ? "bad" : "muted");
export const actionLabel = (a) => (a === "no_action" || a === "hold" ? "hold" : a?.replace("_", " "));
export const regimeTone = (r) => ({ stable: "good", moderate: "warn", volatile: "bad" })[r] ?? "muted";
