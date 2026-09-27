import { cn } from "@/lib/utils";

/** Cadence's InsightBar: mono label + value over a 6px track. `max` 0 renders an empty bar. */
export function InsightBar({
  label,
  value,
  max,
  barClass,
}: {
  label: string;
  value: number;
  max: number;
  barClass: string;
}) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div>
      <div className="mb-1 flex items-center justify-between font-mono text-[11.5px]">
        <span className="text-slate-600">{label}</span>
        <span className="tabular-nums text-muted">{value}</span>
      </div>
      <div
        className="h-1.5 overflow-hidden bg-line"
        role="img"
        aria-label={`${label}: ${value}`}
      >
        <div className={cn("h-full transition-[width] duration-500 ease-out", barClass)} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

/**
 * Cadence's UsageMeter, driven by the real subscription: `used` of `limit` this
 * billing period. Renders nothing when either number is unknown.
 */
export function UsageMeter({
  label,
  used,
  limit,
  resetNote = "Resets each billing period",
  upgradeHref,
  delay = 0,
}: {
  label: string;
  used: number | null | undefined;
  limit: number | null | undefined;
  resetNote?: string;
  upgradeHref?: string;
  delay?: number;
}) {
  if (used == null || limit == null || limit <= 0) return null;
  const pct = Math.min(100, Math.round((used / limit) * 100));
  const near = pct >= 80;
  return (
    <div
      className={cn(
        "border bg-panel px-4 py-3 motion-safe:animate-count-up",
        near ? "border-accent/40" : "border-line"
      )}
      style={delay ? { animationDelay: `${delay}s` } : undefined}
    >
      <div className="flex items-center justify-between font-mono">
        <span className="text-[10px] uppercase tracking-[0.05em] text-muted">{label}</span>
        <span className={cn("text-[10.5px] tabular-nums", near ? "text-accent-text" : "text-muted")}>
          {used}/{limit} used
        </span>
      </div>
      <div className="mt-2 h-1 overflow-hidden bg-line">
        <div
          className={cn("h-full transition-[width] duration-500", near ? "bg-accent" : "bg-sky-500")}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="mt-1 flex items-center justify-between font-mono text-[10px] text-muted">
        <span>{resetNote}</span>
        {near && upgradeHref && (
          <a href={upgradeHref} className="text-[10.5px] text-accent-text underline">
            Upgrade for more →
          </a>
        )}
      </div>
    </div>
  );
}
