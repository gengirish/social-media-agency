"use client";

import { useEffect, useState } from "react";
import { addHours, format, isValid, parseISO, startOfHour } from "date-fns";
import { BellRing, CalendarClock, Loader2, Radio } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PostDialog } from "./dialog";
import { platformLabel } from "./platform";

function defaultSlot(current?: string | null): Date {
  if (current) {
    const d = parseISO(current);
    if (isValid(d) && d.getTime() > Date.now()) return d;
  }
  return startOfHour(addHours(new Date(), 1));
}

const inputClass =
  "w-full rounded-md border border-line bg-canvas px-3 py-2 font-mono text-sm text-ink outline-none transition-colors focus:border-accent";

/**
 * Date + time picker for Schedule and Reschedule. Times are entered in the
 * viewer's local zone and sent as UTC ISO.
 *
 * One dialog, two meanings, and the difference is not cosmetic. On a connected
 * channel the chosen time is when CampaignForge posts to a live account with no
 * second confirmation. On a **manual** channel (`manual`) it posts nothing ever:
 * the time is when it reminds a person to go and post it themselves, and the
 * scheduler's wake interval is capped at up to an hour, so the reminder can land
 * as much as an hour after the minute that was picked. Every word that says or
 * implies "publishes" is therefore branched — a manual reminder that claimed to
 * publish would be the plainest possible breach of product rule 1.
 */
export function ScheduleDialog({
  open,
  mode,
  platform,
  clientName,
  currentAt,
  busy,
  manual = false,
  onConfirm,
  onClose,
}: {
  open: boolean;
  mode: "schedule" | "reschedule";
  platform: string;
  clientName: string | null;
  currentAt?: string | null;
  busy: boolean;
  /** This channel is registered by hand: nothing publishes, the time is a reminder. */
  manual?: boolean;
  onConfirm: (iso: string) => void;
  onClose: () => void;
}) {
  const [date, setDate] = useState("");
  const [time, setTime] = useState("");

  useEffect(() => {
    if (!open) return;
    const d = defaultSlot(currentAt);
    setDate(format(d, "yyyy-MM-dd"));
    setTime(format(d, "HH:mm"));
  }, [open, currentAt]);

  const when = date && time ? new Date(`${date}T${time}`) : null;
  const valid = when !== null && isValid(when);
  const inPast = valid && when.getTime() <= Date.now();
  const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;

  return (
    <PostDialog
      open={open}
      onOpenChange={(o) => !o && onClose()}
      busy={busy}
      title={
        manual
          ? mode === "schedule"
            ? "Set a reminder to post it yourself"
            : "Move this reminder"
          : mode === "schedule"
            ? "Schedule post"
            : "Reschedule post"
      }
      description={`${platformLabel(platform)}${clientName ? ` · ${clientName}` : ""}${
        manual ? " · you post it, we remind you" : ""
      }`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={() => valid && onConfirm(when.toISOString())} disabled={busy || !valid || inPast}>
            {busy ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : manual ? (
              <BellRing className="h-4 w-4" />
            ) : (
              <CalendarClock className="h-4 w-4" />
            )}
            {manual
              ? mode === "schedule"
                ? "Set reminder"
                : "Move reminder"
              : mode === "schedule"
                ? "Schedule"
                : "Reschedule"}
          </Button>
        </>
      }
    >
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="space-y-1.5">
          <span className="text-xs font-medium text-muted">Date</span>
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} className={inputClass} />
        </label>
        <label className="space-y-1.5">
          <span className="text-xs font-medium text-muted">Time</span>
          <input type="time" value={time} onChange={(e) => setTime(e.target.value)} className={inputClass} />
        </label>
      </div>
      <p className="mt-2 font-mono text-[11px] text-muted">
        {valid
          ? `${manual ? "around " : ""}${format(when, "EEE d MMM yyyy, HH:mm")}`
          : "Pick a date and time"}{" "}
        · {zone}
      </p>
      {inPast && <p className="mt-2 text-xs text-red-600">That time has already passed — pick a later one.</p>}

      {manual ? (
        <div className="mt-4 space-y-2 rounded-lg border border-line bg-canvas/60 p-3 text-xs text-slate-700">
          <p className="flex gap-2.5">
            <BellRing className="mt-0.5 h-4 w-4 shrink-0 text-accent-text" aria-hidden />
            <span>
              Nothing goes out at this time. {clientName ? `${clientName}'s` : "This client's"}{" "}
              {platformLabel(platform)} page is one you manage yourself, so CampaignForge holds no access to it — this
              only reminds you to open {platformLabel(platform)} and post it. You still record it here afterwards with
              &ldquo;Post it yourself&rdquo;.
            </span>
          </p>
          <p className="pl-[1.625rem] text-[11px] leading-snug text-muted">
            The reminder can arrive up to an hour late — reminders are sent on a wake-up that runs at most hourly, so
            treat the time as approximate and pick it a little early if the hour matters. It reaches you in the app,
            and in Slack if this workspace has a channel set up. No email is sent.
          </p>
          <p className="pl-[1.625rem] text-[11px] leading-snug text-muted">
            Nothing is charged now; recording the post afterwards is what counts one post against your plan.
          </p>
        </div>
      ) : (
        <div className="mt-4 flex gap-2.5 rounded-lg border border-amber-300 bg-amber-50 p-3 text-xs text-amber-800">
          <Radio className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          <p>
            At this time CampaignForge publishes to {clientName ? `${clientName}'s` : "the client's"} live, connected{" "}
            {platformLabel(platform)} account. There is no second confirmation — reschedule before then if anything
            changes.
          </p>
        </div>
      )}
    </PostDialog>
  );
}
