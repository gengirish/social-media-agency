import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/utils";

/** Frosted glass surface — the Cadence card. */
export function Panel({ className, dashed, ...props }: HTMLAttributes<HTMLDivElement> & { dashed?: boolean }) {
  return (
    <div
      className={cn(
        "rounded-xl border bg-panel/70 shadow-soft backdrop-blur-xl",
        dashed ? "border-dashed border-slate-300 bg-panel/50 shadow-none" : "border-line",
        className
      )}
      {...props}
    />
  );
}

/** Small label with the drawn amber rule in front of it. */
export function Eyebrow({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("flex items-center gap-2 text-xs font-medium tracking-wide text-muted", className)}>
      <span aria-hidden className="h-px w-3.5 animate-draw-in bg-accent" />
      {children}
    </div>
  );
}

/** Page title block: eyebrow, display-face H1, one-line description, actions on the right. */
export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div className="space-y-1.5">
        {eyebrow && <Eyebrow>{eyebrow}</Eyebrow>}
        <h1 className="font-display text-2xl font-semibold tracking-tight text-ink sm:text-3xl">{title}</h1>
        {description && <p className="max-w-2xl text-sm text-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
