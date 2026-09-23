"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { format, isValid, parseISO } from "date-fns";
import { AlertTriangle, CalendarClock, CheckCircle2, Loader2, PenLine } from "lucide-react";
import type { CalendarPost } from "@/lib/api-posts";
import { PLATFORM_LIMITS } from "@/lib/api-posts";
import { publishUnavailableReason } from "@/lib/platforms";
import { Button, buttonVariants } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/status-badge";
import { cn } from "@/lib/utils";
import { PostDialog } from "./dialog";
import { platformLabel, platformTone } from "./platform";

/**
 * Cadence's EventModal: read, edit, and the keyboard-accessible reschedule
 * path (drag-and-drop has no keyboard equivalent on its own).
 */
export function EventModal({
  event,
  clientName,
  busy,
  onClose,
  onEdit,
  onReschedule,
}: {
  event: CalendarPost | null;
  clientName: string | null;
  busy: boolean;
  onClose: () => void;
  onEdit: (event: CalendarPost, body: string) => void;
  onReschedule: (event: CalendarPost) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");

  useEffect(() => {
    setEditing(false);
    setDraft(event?.body ?? "");
  }, [event]);

  const at = event?.scheduled_at ? parseISO(event.scheduled_at) : null;
  const when = at && isValid(at) ? at : null;
  const blocked = event ? publishUnavailableReason(event.platform) : null;
  const gated = event?.status === "approved" || event?.status === "scheduled";
  const limit = event ? PLATFORM_LIMITS[event.platform?.toLowerCase()] ?? null : null;

  return (
    <PostDialog
      open={event !== null}
      onOpenChange={(o) => {
        if (o) return;
        if (editing) setEditing(false);
        else onClose();
      }}
      busy={busy}
      className="max-w-lg"
      title={
        event ? (
          <span className="flex items-center gap-2">
            <span className="flex h-7 w-7 items-center justify-center rounded-md border border-line">
              <span aria-hidden className={cn("h-2.5 w-2.5 rounded-full", platformTone(event.platform).dot)} />
            </span>
            <span className="text-base">{platformLabel(event.platform)}</span>
          </span>
        ) : (
          "Post"
        )
      }
      description={
        event ? (
          <span className="flex flex-wrap items-center gap-2">
            <StatusBadge status={event.status} />
            {clientName && <span className="text-xs text-ink">{clientName}</span>}
            {when && (
              <span className="flex items-center gap-1 font-mono text-[11px] text-sky-600">
                <CalendarClock className="h-3 w-3" />
                {event.status === "draft" || event.status === "approved" ? "Planned " : ""}
                {format(when, "EEE d MMM, HH:mm")}
              </span>
            )}
          </span>
        ) : null
      }
      footer={
        event &&
        (editing ? (
          <>
            <Button variant="secondary" size="sm" onClick={() => setEditing(false)} disabled={busy}>
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={() => draft.trim() && onEdit(event, draft.trim())}
              disabled={busy || !draft.trim() || (limit !== null && draft.length > limit)}
            >
              {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
              {gated ? "Save & send back to Pending" : "Save & close"}
            </Button>
          </>
        ) : (
          <>
            <Button variant="secondary" size="sm" onClick={onClose}>
              Close
            </Button>
            {event.status !== "published" && event.status !== "failed" && (
              <Button variant="secondary" size="sm" onClick={() => setEditing(true)}>
                <PenLine className="h-3.5 w-3.5" /> Edit
              </Button>
            )}
            {gated && (
              <Button
                size="sm"
                onClick={() => onReschedule(event)}
                disabled={blocked !== null}
                title={blocked ?? undefined}
              >
                <CalendarClock className="h-3.5 w-3.5" />
                {event.status === "approved" ? "Schedule" : "Reschedule"}
              </Button>
            )}
            {(event.status === "draft" || event.status === "failed") && (
              <Link href="/content" className={buttonVariants({ size: "sm" })}>
                Open in Queue
              </Link>
            )}
          </>
        ))
      }
    >
      {event && editing ? (
        <>
          {gated && (
            <p className="mb-3 flex gap-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600" aria-hidden />
              Saving sends this post back to Pending — it&apos;s re-checked by moderation, needs approval again
              {event.status === "scheduled" ? ", and its scheduled time is cleared" : ""}.
            </p>
          )}
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={6}
            autoFocus
            className="w-full resize-y rounded-md border border-accent bg-panel px-3 py-2.5 text-[13px] leading-relaxed text-ink outline-none"
          />
          <div className="mt-1 text-right font-mono text-[10px] text-muted">
            {draft.length}
            {limit ? ` / ${limit}` : ""} chars
          </div>
        </>
      ) : (
        event && (
          <>
            {event.title && <p className="font-display text-sm font-semibold text-ink">{event.title}</p>}
            <p className="mt-1 max-h-60 overflow-y-auto whitespace-pre-wrap text-[13px] leading-relaxed text-slate-600">
              {event.body}
            </p>
            {event.hashtags?.length > 0 && (
              <p className="mt-2 font-mono text-xs text-accent-text">{event.hashtags.map((t) => `#${t}`).join(" ")}</p>
            )}
            {event.status === "draft" && (
              <p className="mt-3 text-xs text-muted">
                Pending — approve it in the Queue (moderation runs first) before it can be scheduled.
              </p>
            )}
            {blocked && gated && <p className="mt-3 text-xs text-amber-800">{blocked}</p>}
            {event.status === "published" && (
              <p className="mt-3 flex items-center gap-1 text-xs text-emerald-600">
                <CheckCircle2 className="h-3.5 w-3.5" /> Published — it can no longer be edited here.
              </p>
            )}
          </>
        )
      )}
    </PostDialog>
  );
}
