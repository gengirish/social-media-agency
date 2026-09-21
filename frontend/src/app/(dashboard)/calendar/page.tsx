"use client";

import { useCallback, useEffect, useMemo, useState, type DragEvent } from "react";
import {
  addMonths,
  addWeeks,
  eachDayOfInterval,
  endOfMonth,
  endOfWeek,
  format,
  isSameMonth,
  isToday,
  isValid,
  parseISO,
  startOfMonth,
  startOfWeek,
  subMonths,
  subWeeks,
} from "date-fns";
import { ChevronLeft, ChevronRight, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { api, type CalendarEntry } from "@/lib/api";
import { PageHeader, Panel } from "@/components/ui/panel";
import { StatusBadge } from "@/components/ui/status-badge";
import { PostDialog } from "@/components/posts/dialog";
import { platformLabel, platformTone } from "@/components/posts/platform";

function platformPillClass(platform: string) {
  return cn("border-l-2", platformTone(platform).pill);
}

const PLATFORM_LEGEND: { key: string; label: string }[] = [
  { key: "linkedin", label: "LinkedIn" },
  { key: "twitter", label: "X" },
  { key: "instagram", label: "Instagram" },
  { key: "facebook", label: "Facebook" },
  { key: "tiktok", label: "TikTok" },
  { key: "other", label: "Other" },
];

const CAL_DRAG_TYPE = "application/x-campaignforge-content";

function dayKey(d: Date) {
  return format(d, "yyyy-MM-dd");
}

type CalendarView = "month" | "week";

export default function CalendarPage() {
  const [view, setView] = useState<CalendarView>("month");
  const [currentMonth, setCurrentMonth] = useState(() => startOfMonth(new Date()));
  const [weekStart, setWeekStart] = useState(() => startOfWeek(new Date(), { weekStartsOn: 0 }));
  const [entries, setEntries] = useState<CalendarEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<CalendarEntry | null>(null);

  const loadRange = useCallback(
    async (opts: { mode: CalendarView; month: Date; weekAnchor: Date }) => {
      let start: Date;
      let end: Date;
      if (opts.mode === "month") {
        const monthStart = startOfMonth(opts.month);
        const monthEnd = endOfMonth(opts.month);
        start = startOfWeek(monthStart, { weekStartsOn: 0 });
        end = endOfWeek(monthEnd, { weekStartsOn: 0 });
      } else {
        start = startOfWeek(opts.weekAnchor, { weekStartsOn: 0 });
        end = endOfWeek(opts.weekAnchor, { weekStartsOn: 0 });
      }
      const startStr = format(start, "yyyy-MM-dd");
      const endStr = format(end, "yyyy-MM-dd");
      setLoading(true);
      try {
        const { items } = await api.getCalendar(startStr, endStr);
        setEntries(items);
      } catch (err: unknown) {
        toast.error(err instanceof Error ? err.message : "Failed to load calendar");
        setEntries([]);
      } finally {
        setLoading(false);
      }
    },
    []
  );

  useEffect(() => {
    loadRange({ mode: view, month: currentMonth, weekAnchor: weekStart });
  }, [currentMonth, weekStart, view, loadRange]);

  const monthStart = startOfMonth(currentMonth);
  const monthEnd = endOfMonth(currentMonth);
  const calStart = startOfWeek(monthStart, { weekStartsOn: 0 });
  const calEnd = endOfWeek(monthEnd, { weekStartsOn: 0 });
  const monthGridDays = eachDayOfInterval({ start: calStart, end: calEnd });
  const weekGridStart = startOfWeek(weekStart, { weekStartsOn: 0 });
  const weekGridEnd = endOfWeek(weekStart, { weekStartsOn: 0 });
  const weekGridDays = eachDayOfInterval({ start: weekGridStart, end: weekGridEnd });
  const gridDays = view === "month" ? monthGridDays : weekGridDays;
  const headerLabel =
    view === "month"
      ? format(currentMonth, "MMMM yyyy")
      : `${format(weekGridStart, "MMM d")} – ${format(weekGridEnd, "MMM d, yyyy")}`;

  const byDay = useMemo(() => {
    const map = new Map<string, CalendarEntry[]>();
    for (const e of entries) {
      if (!e.scheduled_at) continue;
      const d = parseISO(e.scheduled_at);
      if (!isValid(d)) continue;
      const k = dayKey(d);
      const list = map.get(k) ?? [];
      list.push(e);
      map.set(k, list);
    }
    return map;
  }, [entries]);

  const weekDays = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

  function buildRescheduledIso(targetDay: Date, entry: CalendarEntry): string {
    let hours = 12;
    let minutes = 0;
    if (entry.scheduled_at) {
      const prev = parseISO(entry.scheduled_at);
      if (isValid(prev)) {
        hours = prev.getHours();
        minutes = prev.getMinutes();
      }
    }
    const d = new Date(targetDay);
    d.setHours(hours, minutes, 0, 0);
    return d.toISOString();
  }

  const handleDragStart = (e: DragEvent, item: CalendarEntry) => {
    e.dataTransfer.setData(CAL_DRAG_TYPE, JSON.stringify({ id: item.id, scheduled_at: item.scheduled_at }));
    e.dataTransfer.effectAllowed = "move";
  };

  const handleDragOverDay = (e: DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
  };

  const handleDropOnDay = async (e: DragEvent, targetDay: Date) => {
    e.preventDefault();
    const raw = e.dataTransfer.getData(CAL_DRAG_TYPE);
    if (!raw) return;
    let payload: { id: string; scheduled_at: string | null };
    try {
      payload = JSON.parse(raw) as { id: string; scheduled_at: string | null };
    } catch {
      return;
    }
    const entry = entries.find((x) => x.id === payload.id);
    const scheduledAt = buildRescheduledIso(
      targetDay,
      entry ?? { ...payload, title: "", platform: "", status: "" }
    );
    try {
      await api.rescheduleContent(payload.id, scheduledAt);
      toast.success("Rescheduled");
      await loadRange({ mode: view, month: currentMonth, weekAnchor: weekStart });
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Could not reschedule");
    }
  };

  const navButton =
    "press-scale flex h-9 w-9 items-center justify-center rounded-md border border-line text-muted transition-colors hover:border-slate-300 hover:bg-slate-500/10 hover:text-ink";

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Posts"
        title="Content Calendar"
        description="Scheduled and published posts by day. Drag a post to another day to reschedule it — the time of day is kept."
        actions={
          <>
            <div role="group" aria-label="Calendar view" className="flex rounded-lg border border-line bg-panel/60 p-1">
              {(["month", "week"] as const).map((v) => (
                <button
                  key={v}
                  type="button"
                  aria-pressed={view === v}
                  onClick={() => {
                    if (v === view) return;
                    if (v === "month") {
                      setView("month");
                      setCurrentMonth(startOfMonth(weekStart));
                    } else {
                      setView("week");
                      setWeekStart(startOfWeek(currentMonth, { weekStartsOn: 0 }));
                    }
                  }}
                  className={cn(
                    "rounded-md px-3 py-1 text-xs font-medium capitalize transition-colors",
                    view === v
                      ? "bg-accent/15 text-ink shadow-[inset_0_0_0_1px_rgb(var(--c-accent)/0.45)]"
                      : "text-muted hover:text-ink"
                  )}
                >
                  {v}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => {
                  if (view === "month") setCurrentMonth((m) => subMonths(m, 1));
                  else setWeekStart((w) => subWeeks(w, 1));
                }}
                className={navButton}
                aria-label={view === "month" ? "Previous month" : "Previous week"}
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              <span className="min-w-[11rem] text-center font-display text-sm font-semibold text-ink">{headerLabel}</span>
              <button
                type="button"
                onClick={() => {
                  if (view === "month") setCurrentMonth((m) => addMonths(m, 1));
                  else setWeekStart((w) => addWeeks(w, 1));
                }}
                className={navButton}
                aria-label={view === "month" ? "Next month" : "Next week"}
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </>
        }
      />

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted">
        {PLATFORM_LEGEND.map(({ key, label }) => (
          <span key={key} className="inline-flex items-center gap-1.5">
            <span aria-hidden className={cn("h-2 w-2 rounded-full", platformTone(key).dot)} />
            {label}
          </span>
        ))}
      </div>

      <Panel className="relative overflow-hidden">
        {loading && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-panel/60 backdrop-blur-sm">
            <Loader2 className="h-6 w-6 animate-spin text-accent" />
          </div>
        )}

        <div className="overflow-x-auto">
          <div className="min-w-[44rem]">
            <div className="grid grid-cols-7 border-b border-line">
              {weekDays.map((d) => (
                <div key={d} className="px-2 py-2.5 text-center font-mono text-[11px] font-medium uppercase tracking-wide text-muted">
                  {d}
                </div>
              ))}
            </div>

            <div className="grid grid-cols-7">
              {gridDays.map((day) => {
                const k = dayKey(day);
                const dayEntries = byDay.get(k) ?? [];
                const inMonth = view === "week" || isSameMonth(day, currentMonth);
                return (
                  <div
                    key={k}
                    onDragOver={handleDragOverDay}
                    onDrop={(e) => handleDropOnDay(e, day)}
                    className={cn(
                      "border-b border-r border-line p-1.5 transition-colors hover:bg-accent/5 [&:nth-child(7n)]:border-r-0",
                      view === "week" ? "min-h-[16rem]" : "min-h-[7.5rem]",
                      !inMonth && "bg-slate-500/5"
                    )}
                  >
                    <div
                      className={cn(
                        "mb-1 flex h-6 w-6 items-center justify-center rounded-full font-mono text-[11px] font-medium",
                        isToday(day)
                          ? "bg-accent text-on-accent"
                          : inMonth
                            ? "text-ink"
                            : "text-slate-400"
                      )}
                    >
                      {format(day, "d")}
                    </div>
                    <div
                      className={cn(
                        "flex flex-col gap-1 overflow-y-auto",
                        view === "week" ? "max-h-[14rem]" : "max-h-[5rem]"
                      )}
                    >
                      {dayEntries.map((item) => (
                        <button
                          key={item.id}
                          type="button"
                          draggable
                          onDragStart={(e) => handleDragStart(e, item)}
                          onClick={() => setSelected(item)}
                          className={cn(
                            "cursor-grab truncate rounded px-1.5 py-1 text-left text-[11px] font-medium leading-tight transition-colors active:cursor-grabbing",
                            platformPillClass(item.platform)
                          )}
                        >
                          {item.title || "Untitled"}
                        </button>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </Panel>

      <PostDialog
        open={selected !== null}
        onOpenChange={(o) => !o && setSelected(null)}
        className="max-w-lg"
        title={selected?.title || "Untitled"}
        description={
          selected ? (
            <span className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1.5">
                <span aria-hidden className={cn("h-2 w-2 rounded-full", platformTone(selected.platform).dot)} />
                {platformLabel(selected.platform)}
              </span>
              {selected.scheduled_at && isValid(parseISO(selected.scheduled_at)) && (
                <span className="font-mono text-xs">{format(parseISO(selected.scheduled_at), "PPp")}</span>
              )}
              <StatusBadge status={selected.status} />
            </span>
          ) : null
        }
      >
        {selected?.body && (
          <p className="max-h-60 overflow-y-auto whitespace-pre-wrap rounded-lg border border-line bg-canvas/60 p-3 text-sm leading-relaxed text-slate-700">
            {selected.body}
          </p>
        )}
      </PostDialog>
    </div>
  );
}

