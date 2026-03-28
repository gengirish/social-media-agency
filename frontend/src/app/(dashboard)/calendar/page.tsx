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
import { ChevronLeft, ChevronRight, Loader2, X } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { api, type CalendarEntry } from "@/lib/api";

function platformPillClass(platform: string) {
  const p = platform.toLowerCase();
  if (p === "linkedin") return "bg-indigo-100 text-indigo-800 border-l-4 border-l-indigo-500 border-indigo-200 hover:bg-indigo-200/80";
  if (p === "twitter" || p === "x")
    return "bg-sky-100 text-sky-800 border-l-4 border-l-sky-500 border-sky-200 hover:bg-sky-200/80";
  if (p === "instagram") return "bg-pink-100 text-pink-800 border-l-4 border-l-pink-500 border-pink-200 hover:bg-pink-200/80";
  if (p === "facebook" || p === "meta")
    return "bg-blue-100 text-blue-800 border-l-4 border-l-blue-600 border-blue-200 hover:bg-blue-200/80";
  if (p === "tiktok") return "bg-slate-100 text-slate-800 border-l-4 border-l-slate-600 border-slate-200 hover:bg-slate-200/80";
  return "bg-slate-100 text-slate-700 border-l-4 border-l-slate-400 border-slate-200 hover:bg-slate-200/80";
}

const PLATFORM_LEGEND: { key: string; label: string }[] = [
  { key: "linkedin", label: "LinkedIn" },
  { key: "twitter", label: "X / Twitter" },
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

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Content Calendar</h1>
          <p className="mt-1 text-slate-500">Scheduled and published posts by day</p>
          <div className="mt-3 flex flex-wrap items-center gap-3 text-xs">
            <span className="font-semibold text-slate-600">Platforms:</span>
            {PLATFORM_LEGEND.map(({ key, label }) => (
              <span
                key={key}
                className={cn(
                  "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 font-medium capitalize",
                  platformPillClass(key)
                )}
              >
                {label}
              </span>
            ))}
          </div>
        </div>
        <div className="flex flex-col items-stretch gap-3 sm:flex-row sm:items-center sm:flex-wrap sm:justify-end">
          <div className="flex rounded-lg border border-slate-200 bg-slate-50 p-0.5">
            <button
              type="button"
              onClick={() => {
                setView("month");
                setCurrentMonth(startOfMonth(weekStart));
              }}
              className={cn(
                "rounded-md px-3 py-1.5 text-xs font-semibold transition-colors",
                view === "month" ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"
              )}
            >
              Month
            </button>
            <button
              type="button"
              onClick={() => {
                setView("week");
                setWeekStart(startOfWeek(currentMonth, { weekStartsOn: 0 }));
              }}
              className={cn(
                "rounded-md px-3 py-1.5 text-xs font-semibold transition-colors",
                view === "week" ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"
              )}
            >
              Week
            </button>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => {
                if (view === "month") setCurrentMonth((m) => subMonths(m, 1));
                else setWeekStart((w) => subWeeks(w, 1));
              }}
              className="rounded-lg border border-slate-200 bg-white p-2 text-slate-600 shadow-sm hover:bg-slate-50"
              aria-label={view === "month" ? "Previous month" : "Previous week"}
            >
              <ChevronLeft className="h-5 w-5" />
            </button>
            <span className="min-w-[12rem] text-center text-sm font-semibold text-slate-900">{headerLabel}</span>
            <button
              type="button"
              onClick={() => {
                if (view === "month") setCurrentMonth((m) => addMonths(m, 1));
                else setWeekStart((w) => addWeeks(w, 1));
              }}
              className="rounded-lg border border-slate-200 bg-white p-2 text-slate-600 shadow-sm hover:bg-slate-50"
              aria-label={view === "month" ? "Next month" : "Next week"}
            >
              <ChevronRight className="h-5 w-5" />
            </button>
          </div>
        </div>
      </div>

      <div className="relative rounded-xl border border-slate-200 bg-white shadow-sm">
        {loading && (
          <div className="absolute inset-0 z-10 flex items-center justify-center rounded-xl bg-white/70 backdrop-blur-sm">
            <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
          </div>
        )}

        <div className="grid grid-cols-7 border-b border-slate-100">
          {weekDays.map((d) => (
            <div key={d} className="px-2 py-3 text-center text-xs font-semibold uppercase text-slate-500">
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
                  "min-h-[7.5rem] border-b border-r border-slate-100 p-1.5 transition-colors last:border-r-0",
                  !inMonth && "bg-slate-50/80",
                  "hover:bg-indigo-50/30"
                )}
              >
                <div
                  className={cn(
                    "mb-1 flex h-7 w-7 items-center justify-center rounded-full text-xs font-medium",
                    isToday(day) ? "bg-indigo-600 text-white" : inMonth ? "text-slate-900" : "text-slate-400"
                  )}
                >
                  {format(day, "d")}
                </div>
                <div className="flex max-h-[5rem] flex-col gap-1 overflow-y-auto">
                  {dayEntries.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      draggable
                      onDragStart={(e) => handleDragStart(e, item)}
                      onClick={() => setSelected(item)}
                      className={cn(
                        "cursor-grab truncate rounded-md border px-1.5 py-0.5 text-left text-[10px] font-medium leading-tight transition-colors active:cursor-grabbing sm:text-xs",
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

      {selected && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <button
            type="button"
            className="absolute inset-0 bg-black/40"
            aria-label="Close modal"
            onClick={() => setSelected(null)}
          />
          <div className="relative z-10 w-full max-w-lg rounded-xl border border-slate-200 bg-white p-6 shadow-xl">
            <button
              type="button"
              onClick={() => setSelected(null)}
              className="absolute right-4 top-4 rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
            >
              <X className="h-5 w-5" />
            </button>
            <span
              className={cn(
                "inline-block rounded-full border px-2 py-0.5 text-xs font-semibold capitalize",
                platformPillClass(selected.platform)
              )}
            >
              {selected.platform}
            </span>
            <h2 className="mt-3 pr-8 text-lg font-bold text-slate-900">{selected.title || "Untitled"}</h2>
            {selected.scheduled_at && isValid(parseISO(selected.scheduled_at)) && (
              <p className="mt-2 text-sm text-slate-500">
                {format(parseISO(selected.scheduled_at), "PPpp")}
              </p>
            )}
            <p className="mt-1 text-xs font-medium uppercase text-slate-400">Status: {selected.status}</p>
            {selected.body && (
              <p className="mt-4 max-h-48 overflow-y-auto whitespace-pre-wrap text-sm text-slate-700">{selected.body}</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
