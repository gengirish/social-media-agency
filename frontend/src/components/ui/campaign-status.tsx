import { cn } from "@/lib/utils";

/* campaign.status, styled like StatusBadge (which covers content_piece.status). */
const CAMPAIGN_STATUS: Record<string, string> = {
  planning: "border-slate-300 bg-slate-100 text-slate-600",
  running: "border-indigo-300 bg-indigo-50 text-accent-text",
  completed: "border-emerald-200 bg-emerald-50 text-emerald-700",
  paused: "border-amber-300 bg-amber-50 text-amber-800",
  failed: "border-red-200 bg-red-50 text-red-700",
};

export function CampaignStatusBadge({ status, className }: { status: string; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2 py-0.5 font-mono text-[11px] font-medium capitalize",
        CAMPAIGN_STATUS[status] ?? CAMPAIGN_STATUS.planning,
        className
      )}
    >
      <span
        aria-hidden
        className={cn("h-1.5 w-1.5 rounded-full bg-current", status === "running" && "motion-safe:animate-pulse-dot")}
      />
      {status}
    </span>
  );
}
