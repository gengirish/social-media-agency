"use client";

import { useEffect, useState } from "react";
import { addHours, format, isValid, parseISO, startOfHour } from "date-fns";
import { CalendarClock, Loader2, Radio } from "lucide-react";
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
 */
export function ScheduleDialog({
  open,
  mode,
  platform,
  clientName,
  currentAt,
  busy,
  onConfirm,
  onClose,
}: {
  open: boolean;
  mode: "schedule" | "reschedule";
  platform: string;
  clientName: string | null;
  currentAt?: string | null;
  busy: boolean;
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
      title={mode === "schedule" ? "Schedule post" : "Reschedule post"}
      description={`${platformLabel(platform)}${clientName ? ` · ${clientName}` : ""}`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={() => valid && onConfirm(when.toISOString())} disabled={busy || !valid || inPast}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <CalendarClock className="h-4 w-4" />}
            {mode === "schedule" ? "Schedule" : "Reschedule"}
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
        {valid ? format(when, "EEE d MMM yyyy, HH:mm") : "Pick a date and time"} · {zone}
      </p>
      {inPast && <p className="mt-2 text-xs text-red-600">That time has already passed — pick a later one.</p>}

      <div className="mt-4 flex gap-2.5 rounded-lg border border-amber-300 bg-amber-50 p-3 text-xs text-amber-800">
        <Radio className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
        <p>
          At this time CampaignForge publishes to {clientName ? `${clientName}'s` : "the client's"} live, connected{" "}
          {platformLabel(platform)} account. There is no second confirmation — reschedule before then if anything
          changes.
        </p>
      </div>
    </PostDialog>
  );
}
