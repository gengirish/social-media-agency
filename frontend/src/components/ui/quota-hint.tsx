import { cn } from "@/lib/utils";

/**
 * "N generations left this month" beside a generate button. Renders nothing when
 * the numbers are unknown — a guessed quota is an invented number.
 *
 * CF-19: the same quota was worded three ways across the app ("generations
 * left", "generations left this period", "left this month"). The default below
 * is the one wording; `noun` remains for a quota that is not generations, such
 * as published posts.
 */
export function QuotaHint({
  used,
  limit,
  noun = "generations left this month",
  className,
}: {
  used: number | null | undefined;
  limit: number | null | undefined;
  noun?: string;
  className?: string;
}) {
  if (used == null || limit == null || limit <= 0) return null;
  const left = Math.max(0, limit - used);
  const low = left <= Math.max(1, Math.floor(limit * 0.1));
  return (
    <span
      className={cn("font-mono text-[11px]", left === 0 ? "text-red-600" : low ? "text-amber-700" : "text-muted", className)}
    >
      {left} {noun}
    </span>
  );
}
