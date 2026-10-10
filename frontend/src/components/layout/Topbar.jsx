import { RANGES, REFRESH_OPTIONS } from "../../config";
import { fmtTime } from "../../lib/format";

function Segmented({ options, value, onChange, getKey, getLabel }) {
  return (
    <div className="inline-flex rounded-md border border-hairline overflow-hidden">
      {options.map((o) => {
        const active = getKey(o) === value;
        return (
          <button
            key={getKey(o)}
            onClick={() => onChange(getKey(o))}
            className={`px-2.5 py-1 text-[11px] font-mono transition ${
              active ? "bg-accent/15 text-accent" : "text-text-muted hover:text-text-primary hover:bg-panel-2"
            }`}
          >
            {getLabel(o)}
          </button>
        );
      })}
    </div>
  );
}

export default function Topbar({ title, clusterName, range, onRange, refreshMs, onRefreshMs, updatedAt, onRefresh, onMenu }) {
  return (
    <header className="sticky top-0 z-20 border-b border-hairline bg-void/90 backdrop-blur px-4 sm:px-6 py-3 flex flex-wrap items-center gap-x-4 gap-y-2">
      <button onClick={onMenu} className="lg:hidden p-1.5 -ml-1 rounded-md border border-hairline text-text-muted" aria-label="Open menu">
        <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <path d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>

      <div className="mr-auto">
        <h2 className="font-display font-semibold text-base leading-tight">{title}</h2>
        <p className="text-[11px] text-text-muted font-mono">{clusterName ?? "no cluster selected"}</p>
      </div>

      <div className="flex items-center gap-2 text-[11px] font-mono text-text-muted">
        <span className="hidden sm:inline">range</span>
        <Segmented options={RANGES} value={range} onChange={onRange} getKey={(o) => o.label} getLabel={(o) => o.label} />
      </div>
      <div className="flex items-center gap-2 text-[11px] font-mono text-text-muted">
        <span className="hidden sm:inline">refresh</span>
        <Segmented options={REFRESH_OPTIONS} value={refreshMs} onChange={onRefreshMs} getKey={(o) => o.ms} getLabel={(o) => o.label} />
        <button onClick={onRefresh} className="px-2 py-1 rounded-md border border-hairline hover:text-accent hover:border-accent/40 transition" title="Refresh now">
          ↻
        </button>
      </div>
      <div className="text-[11px] font-mono text-text-muted w-28 text-right hidden md:block">
        {updatedAt ? `updated ${fmtTime(updatedAt)}` : "connecting…"}
      </div>
    </header>
  );
}
