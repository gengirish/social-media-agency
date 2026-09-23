"use client";

import { Filter } from "lucide-react";
import { platformLabel, platformTone } from "@/components/posts/platform";
import { cn } from "@/lib/utils";

/**
 * Cadence's "Channel" filter row. Pass only platforms that have data behind
 * them (e.g. the client's connected accounts) — offering a channel with
 * nothing in it is a filter that can only ever return empty.
 */
export function PlatformFilterRow({
  platforms,
  value,
  onChange,
  size = "default",
}: {
  platforms: string[];
  value: string;
  onChange: (value: string) => void;
  size?: "default" | "small";
}) {
  const options = ["all", ...platforms];
  return (
    <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Filter by channel">
      <span className="mr-0.5 flex items-center gap-1 font-mono text-[9.5px] uppercase tracking-wider text-muted">
        <Filter aria-hidden className="h-2.5 w-2.5" />
        Channel
      </span>
      {options.map((id) => {
        const active = value === id;
        return (
          <button
            key={id}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(id)}
            className={cn(
              "press-scale flex items-center gap-1.5 rounded-md border font-mono transition-all duration-200",
              size === "small" ? "px-2 py-1 text-[10.5px]" : "px-2.5 py-1.5 text-[11px]",
              active ? "border-accent/50 bg-slate-500/10 text-ink" : "border-line text-muted hover:text-ink"
            )}
          >
            {id !== "all" && <span aria-hidden className={cn("h-1.5 w-1.5 rounded-full", platformTone(id).dot)} />}
            {id === "all" ? "All channels" : platformLabel(id)}
          </button>
        );
      })}
    </div>
  );
}
