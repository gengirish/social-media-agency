import type { ComponentType, ReactNode } from "react";
import { cn } from "@/lib/utils";

/*
 * Cadence's hero stat: a display-face numeral over a short label, on glass.
 * Only ever pass a real number — callers that have none should render "—"
 * (Product rule 4), which this styles as muted.
 */
export function StatCard({
  label,
  value,
  icon: Icon,
  hint,
  tone = "default",
  delay = 0,
  className,
}: {
  label: ReactNode;
  value: ReactNode;
  icon?: ComponentType<{ className?: string }>;
  hint?: ReactNode;
  tone?: "default" | "accent" | "success" | "info";
  delay?: number;
  className?: string;
}) {
  const empty = value === "—" || value == null;
  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-xl border border-line bg-panel/70 p-4 shadow-soft backdrop-blur-xl motion-safe:animate-screen-in sm:p-5",
        className
      )}
      style={delay ? { animationDelay: `${delay}s` } : undefined}
    >
      <div className="flex items-start justify-between gap-3">
        <div
          className={cn(
            "font-display text-3xl font-semibold tabular-nums tracking-tight",
            empty
              ? "text-slate-400"
              : tone === "accent"
                ? "text-accent-text"
                : tone === "success"
                  ? "text-emerald-600"
                  : tone === "info"
                    ? "text-blue-600"
                    : "text-ink"
          )}
        >
          {value ?? "—"}
        </div>
        {Icon && (
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-line text-accent-text">
            <Icon className="h-4 w-4" />
          </span>
        )}
      </div>
      <div className="mt-1.5 text-xs text-muted">{label}</div>
      {hint && <div className="mt-1 font-mono text-[11px] text-muted">{hint}</div>}
    </div>
  );
}
