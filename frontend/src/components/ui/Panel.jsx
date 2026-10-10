export default function Panel({ title, subtitle, right, children, className = "" }) {
  return (
    <section className={`rounded-lg border border-hairline bg-panel p-5 ${className}`}>
      {(title || right) && (
        <div className="flex items-start justify-between gap-3 mb-4">
          <div>
            {title && <h3 className="text-xs font-mono uppercase tracking-wider text-text-muted">{title}</h3>}
            {subtitle && <p className="text-[11px] text-text-muted/70 mt-1">{subtitle}</p>}
          </div>
          {right}
        </div>
      )}
      {children}
    </section>
  );
}

export function Empty({ children }) {
  return (
    <div className="rounded-lg border border-dashed border-hairline bg-panel/60 p-6 text-sm text-text-muted font-mono">
      {children}
    </div>
  );
}

export function ErrorBanner({ children }) {
  return (
    <div className="rounded-lg border border-bad/40 bg-bad/10 text-bad text-sm font-mono p-4">{children}</div>
  );
}
