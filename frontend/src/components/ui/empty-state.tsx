import type { ComponentType, ReactNode } from "react";
import { AlertTriangle, Info, Loader2, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";

/** Dashed glass placeholder for "nothing here yet" — an honest empty state, never fake rows. */
export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: {
  icon?: ComponentType<{ className?: string }>;
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center rounded-xl border border-dashed border-slate-300 bg-panel/50 px-6 py-14 text-center backdrop-blur-xl motion-safe:animate-screen-in",
        className
      )}
    >
      {Icon && (
        <span className="mb-4 flex h-11 w-11 items-center justify-center rounded-xl border border-line bg-panel text-accent-text">
          <Icon className="h-5 w-5" />
        </span>
      )}
      <h3 className="font-display text-base font-semibold text-ink">{title}</h3>
      {description && <p className="mt-1 max-w-sm text-sm text-muted">{description}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

/** Centered spinner with an optional mono caption. */
export function LoadingState({ label, className }: { label?: ReactNode; className?: string }) {
  return (
    <div
      role="status"
      className={cn("flex h-64 flex-col items-center justify-center gap-3 text-muted", className)}
    >
      <Loader2 className="h-6 w-6 animate-spin text-accent-text" aria-hidden />
      <span className={label ? "font-mono text-[11px]" : "sr-only"}>{label ?? "Loading"}</span>
    </div>
  );
}

const NOTICE = {
  warning: { icon: AlertTriangle, box: "border-amber-300/70 bg-amber-50", icon_: "text-amber-600", text: "text-amber-900" },
  danger: { icon: XCircle, box: "border-red-300/70 bg-red-50", icon_: "text-red-600", text: "text-red-800" },
  info: { icon: Info, box: "border-line bg-slate-500/5", icon_: "text-accent-text", text: "text-ink" },
} as const;

/** Inline callout for limits and unavailable features — says what isn't real, plainly. */
export function Notice({
  tone = "warning",
  title,
  children,
  className,
}: {
  tone?: keyof typeof NOTICE;
  title?: ReactNode;
  children?: ReactNode;
  className?: string;
}) {
  const t = NOTICE[tone];
  const Icon = t.icon;
  return (
    <div className={cn("flex gap-3 rounded-lg border p-4 text-sm", t.box, className)}>
      <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", t.icon_)} aria-hidden />
      <div className={cn("min-w-0", t.text)}>
        {title && <p className="font-medium">{title}</p>}
        {children && <div className={cn(title && "mt-1")}>{children}</div>}
      </div>
    </div>
  );
}
