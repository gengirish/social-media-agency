"use client";

import { Search, X } from "lucide-react";
import { cn } from "@/lib/utils";

/** Cadence's compact mono search box with a clear button. */
export function SearchInput({
  value,
  onChange,
  placeholder = "Search…",
  className,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
}) {
  return (
    <div className={cn("relative flex items-center", className)}>
      <Search aria-hidden className="pointer-events-none absolute left-2.5 h-3 w-3 text-muted" />
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        aria-label={placeholder}
        className="w-44 rounded-md border border-line bg-panel/70 py-1.5 pl-7 pr-7 font-mono text-[11px] text-ink outline-none transition-all duration-200 placeholder:text-muted focus:border-accent focus:shadow-[0_0_0_3px_rgb(var(--c-accent)/0.1)]"
      />
      {value && (
        <button
          type="button"
          onClick={() => onChange("")}
          aria-label="Clear search"
          className="absolute right-2 text-muted hover:text-ink"
        >
          <X className="h-3 w-3" />
        </button>
      )}
    </div>
  );
}
