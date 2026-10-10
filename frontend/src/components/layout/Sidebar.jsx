import { fmt, isNum } from "../../lib/format";

export const NAV = [
  {
    section: "Monitor",
    items: [
      { id: "overview", label: "Overview", icon: "M3 3h8v8H3zM13 3h8v5h-8zM13 10h8v11h-8zM3 13h8v8H3z" },
      { id: "pods", label: "Pod Scaling", icon: "M12 2l9 5v10l-9 5-9-5V7zM12 12l9-5M12 12v10M12 12L3 7" },
      { id: "latency", label: "Latency", icon: "M12 6v6l4 2M12 22a10 10 0 100-20 10 10 0 000 20z" },
      { id: "traffic", label: "Traffic & Forecast", icon: "M3 17l6-6 4 4 8-8M15 7h6v6" },
      { id: "resources", label: "Resources", icon: "M4 6h16M4 12h16M4 18h16M8 3v6M16 9v6M10 15v6" },
    ],
  },
  {
    section: "Automation",
    items: [{ id: "decisions", label: "Decisions", icon: "M9 11l3 3L22 4M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" }],
  },
];

function Icon({ d }) {
  return (
    <svg viewBox="0 0 24 24" className="w-4 h-4 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d={d} />
    </svg>
  );
}

export default function Sidebar({ view, onView, clusters, selectedId, onSelectCluster, open, onClose, apiOk }) {
  return (
    <>
      {open && <div className="fixed inset-0 bg-black/60 z-30 lg:hidden" onClick={onClose} />}
      <aside
        className={`fixed lg:sticky top-0 left-0 z-40 h-screen w-64 shrink-0 border-r border-hairline bg-panel flex flex-col transition-transform lg:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="px-5 py-4 border-b border-hairline">
          <h1 className="font-display font-semibold text-lg leading-tight">Orchestrator.control</h1>
          <p className="text-[11px] text-text-muted font-mono mt-0.5 flex items-center gap-1.5">
            <span className={`w-1.5 h-1.5 rounded-full ${apiOk ? "bg-good pulse-dot" : "bg-bad"}`} />
            {apiOk ? "api connected" : "api unreachable"}
          </p>
        </div>

        <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-5">
          {NAV.map((group) => (
            <div key={group.section}>
              <div className="px-2 mb-1.5 text-[10px] font-mono uppercase tracking-wider text-text-muted/70">{group.section}</div>
              <ul className="space-y-0.5">
                {group.items.map((it) => {
                  const active = it.id === view;
                  return (
                    <li key={it.id}>
                      <button
                        onClick={() => {
                          onView(it.id);
                          onClose();
                        }}
                        className={`w-full flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm text-left transition ${
                          active ? "bg-accent/10 text-accent" : "text-text-muted hover:bg-panel-2 hover:text-text-primary"
                        }`}
                      >
                        <Icon d={it.icon} />
                        {it.label}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}

          <div>
            <div className="px-2 mb-1.5 text-[10px] font-mono uppercase tracking-wider text-text-muted/70">Clusters</div>
            <ul className="space-y-0.5">
              {clusters.length === 0 && <li className="px-2.5 py-2 text-xs text-text-muted font-mono">no clusters yet…</li>}
              {clusters.map((c) => {
                const healthy = c.status === "healthy";
                const active = c.id === selectedId;
                return (
                  <li key={c.id}>
                    <button
                      onClick={() => {
                        onSelectCluster(c.id);
                        onClose();
                      }}
                      className={`w-full rounded-md px-2.5 py-2 text-left transition border ${
                        active ? "border-accent/40 bg-panel-2" : "border-transparent hover:bg-panel-2"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-xs text-text-primary">{c.name}</span>
                        <span className={`w-1.5 h-1.5 rounded-full ${healthy ? "bg-good" : "bg-bad"}`} />
                      </div>
                      <div className="mt-1 flex gap-3 text-[10px] font-mono text-text-muted">
                        <span>{isNum(c.pod_count) ? `${c.pod_count} pods (all)` : "— pods"}</span>
                        <span>{isNum(c.latency_ms) ? `${fmt(c.latency_ms, 0)} ms` : "— ms"}</span>
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        </nav>
      </aside>
    </>
  );
}
