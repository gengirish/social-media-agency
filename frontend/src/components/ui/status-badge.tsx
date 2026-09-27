import { cn } from "@/lib/utils";

/*
 * content_piece.status as the UI names it. The database keeps `draft` for
 * anything awaiting review; the product calls that Pending (Cadence's
 * vocabulary), because "draft" undersells that it is waiting on a human.
 */
const STATUS: Record<string, { label: string; className: string }> = {
  draft: { label: "Pending", className: "border-amber-300 bg-amber-50 text-amber-800" },
  approved: { label: "Approved", className: "border-blue-200 bg-blue-50 text-blue-700" },
  scheduled: { label: "Scheduled", className: "border-violet-200 bg-violet-50 text-violet-700" },
  published: { label: "Published", className: "border-emerald-200 bg-emerald-50 text-emerald-700" },
  failed: { label: "Failed", className: "border-red-200 bg-red-50 text-red-700" },
  rejected: { label: "Rejected", className: "border-slate-300 bg-slate-100 text-slate-600" },
};

export function statusLabel(status: string): string {
  return STATUS[status]?.label ?? status;
}

export function StatusBadge({ status, className }: { status: string; className?: string }) {
  const s = STATUS[status] ?? { label: status, className: "border-slate-300 bg-slate-100 text-slate-600" };
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 font-mono text-[11px] font-medium",
        s.className,
        className
      )}
    >
      <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-current" />
      {s.label}
    </span>
  );
}
