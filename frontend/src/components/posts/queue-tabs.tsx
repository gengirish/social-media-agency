"use client";

import type { QueueStatus } from "@/lib/api";
import { cn } from "@/lib/utils";

export const QUEUE_TABS: { status: QueueStatus; label: string }[] = [
  { status: "draft", label: "Pending" },
  { status: "approved", label: "Approved" },
  { status: "scheduled", label: "Scheduled" },
  { status: "published", label: "Published" },
  { status: "failed", label: "Failed" },
];

/** Status tabs. A count of `null` means "not loaded" and renders as a dash, never a guess. */
export function QueueTabs({
  active,
  counts,
  onChange,
}: {
  active: QueueStatus;
  counts: Partial<Record<QueueStatus, number | null>>;
  onChange: (status: QueueStatus) => void;
}) {
  return (
    <div
      role="tablist"
      aria-label="Post status"
      className="-mx-4 flex gap-1 overflow-x-auto px-4 sm:mx-0 sm:px-0"
    >
      <div className="flex gap-1 rounded-lg border border-line bg-panel/60 p-1 backdrop-blur">
        {QUEUE_TABS.map(({ status, label }) => {
          const selected = status === active;
          const count = counts[status];
          const alert = status === "failed" && (count ?? 0) > 0;
          return (
            <button
              key={status}
              type="button"
              role="tab"
              aria-selected={selected}
              onClick={() => onChange(status)}
              className={cn(
                "press-scale flex shrink-0 items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                selected ? "bg-accent/15 text-ink shadow-[inset_0_0_0_1px_rgb(var(--c-accent)/0.45)]" : "text-muted hover:bg-slate-500/10 hover:text-ink"
              )}
            >
              {label}
              <span
                className={cn(
                  "min-w-[1.5rem] rounded-full px-1.5 py-px text-center font-mono text-[11px]",
                  alert
                    ? "bg-red-100 text-red-700"
                    : selected
                      ? "bg-accent text-on-accent"
                      : "bg-slate-500/10 text-muted"
                )}
              >
                {count == null ? "–" : count}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
