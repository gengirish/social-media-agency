"use client";

import { AlertTriangle, Loader2 } from "lucide-react";
import type { ModerationIssue } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { PostDialog } from "./dialog";

const SEVERITY: Record<string, string> = {
  critical: "border-red-200 bg-red-50 text-red-700",
  high: "border-red-200 bg-red-50 text-red-700",
  medium: "border-amber-300 bg-amber-50 text-amber-800",
  warning: "border-amber-300 bg-amber-50 text-amber-800",
  low: "border-slate-300 bg-slate-100 text-slate-600",
  info: "border-slate-300 bg-slate-100 text-slate-600",
};

/**
 * Shown when approve returns 409 `moderation_flagged`. Editing is the primary
 * path; "Approve anyway" is deliberately secondary and is recorded server-side
 * as an override.
 */
export function ModerationWarning({
  open,
  postTitle,
  issues,
  busy,
  onEdit,
  onOverride,
  onClose,
}: {
  open: boolean;
  postTitle: string;
  issues: ModerationIssue[];
  busy: boolean;
  onEdit: () => void;
  onOverride: () => void;
  onClose: () => void;
}) {
  return (
    <PostDialog
      open={open}
      onOpenChange={(o) => !o && onClose()}
      busy={busy}
      tone="warning"
      title={
        <span className="flex items-center gap-2">
          <AlertTriangle className="h-5 w-5 shrink-0 text-amber-600" aria-hidden />
          Moderation flagged this post
        </span>
      }
      description={
        <>
          The check found {issues.length === 1 ? "an issue" : `${issues.length} issues`} in &ldquo;
          {postTitle || "Untitled post"}&rdquo;. It stays Pending until you edit it or approve it anyway.
        </>
      }
      footer={
        <>
          <Button variant="secondary" onClick={onOverride} disabled={busy}>
            {busy && <Loader2 className="h-4 w-4 animate-spin" />}
            Approve anyway
          </Button>
          <Button onClick={onEdit} disabled={busy} autoFocus>
            Go back and edit
          </Button>
        </>
      }
    >
      {issues.length > 0 ? (
        <ul className="space-y-2">
          {issues.map((issue, i) => (
            <li key={i} className="flex items-start gap-3 rounded-lg border border-line bg-canvas/60 p-3">
              <span
                className={cn(
                  "mt-0.5 shrink-0 rounded-full border px-2 py-0.5 font-mono text-[10px] font-medium uppercase",
                  SEVERITY[issue.severity?.toLowerCase()] ?? SEVERITY.info
                )}
              >
                {issue.severity || "issue"}
              </span>
              <p className="text-sm text-ink">{issue.message}</p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="rounded-lg border border-line bg-canvas/60 p-3 text-sm text-muted">
          The check did not return details for its objection.
        </p>
      )}
      <p className="mt-3 text-xs text-muted">Approving anyway is logged against your account.</p>
    </PostDialog>
  );
}
