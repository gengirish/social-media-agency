import type { ComponentType, ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface TabItem<T extends string> {
  id: T;
  label: ReactNode;
  icon?: ComponentType<{ className?: string }>;
}

/*
 * Segmented control for in-page views. Rendered as plain buttons with
 * aria-pressed (not an ARIA tablist): callers own the panels, and several E2E
 * specs locate these by role "button".
 */
export function SegmentedTabs<T extends string>({
  items,
  value,
  onChange,
  className,
  stretch,
  label,
}: {
  items: TabItem<T>[];
  value: T;
  onChange: (id: T) => void;
  className?: string;
  stretch?: boolean;
  label?: string;
}) {
  return (
    <div
      role="group"
      aria-label={label}
      className={cn(
        "flex max-w-full gap-1 overflow-x-auto rounded-lg border border-line bg-panel/60 p-1 backdrop-blur-xl",
        stretch ? "w-full" : "w-fit",
        className
      )}
    >
      {items.map((item) => {
        const active = item.id === value;
        const Icon = item.icon;
        return (
          <button
            key={item.id}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(item.id)}
            className={cn(
              "press-scale flex shrink-0 items-center justify-center gap-1.5 whitespace-nowrap rounded-md px-3.5 py-1.5 text-[13px] font-medium transition-colors duration-200",
              stretch && "flex-1",
              active
                ? "bg-accent text-on-accent shadow-[0_2px_10px_rgb(var(--c-accent)/0.25)]"
                : "text-muted hover:bg-slate-500/10 hover:text-ink"
            )}
          >
            {Icon && <Icon className="h-3.5 w-3.5" />}
            {item.label}
          </button>
        );
      })}
    </div>
  );
}

/** Small mono chip — channels, platforms, categories. */
export function Tag({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md border border-line bg-slate-500/5 px-2 py-0.5 font-mono text-[11px] text-muted",
        className
      )}
    >
      {children}
    </span>
  );
}
