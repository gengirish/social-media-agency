"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  addMonths,
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
} from "date-fns";
import { ChevronLeft, ChevronRight, Loader2, X } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { api, type CalendarEntry } from "@/lib/api";

function platformPillClass(platform: string) {
  const p = platform.toLowerCase();
  if (p === "linkedin") return "bg-indigo-100 text-indigo-800 border-indigo-200 hover:bg-indigo-200/80";
  if (p === "twitter") return "bg-sky-100 text-sky-800 border-sky-200 hover:bg-sky-200/80";
  if (p === "instagram") return "bg-pink-100 text-pink-800 border-pink-200 hover:bg-pink-200/80";
  if (p === "facebook") return "bg-blue-100 text-blue-800 border-blue-200 hover:bg-blue-200/80";
  return "bg-slate-100 text-slate-700 border-slate-200 hover:bg-slate-200/80";
}

function dayKey(d: Date) {
  return format(d, "yyyy-MM-dd");
}

export default function CalendarPage() {
  const [currentMonth, setCurrentMonth] = useState(() => startOfMonth(new Date()));
  const [entries, setEntries] = useState<CalendarEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<CalendarEntry | null>(null);

  const loadRange = useCallback(async (month: Date) => {
    const start = startOfWeek(startOfMonth(month), { weekStartsOn: 0 });
    const end = endOfWeek(endOfMonth(month), { weekStartsOn: 0 });
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
  }, []);

  useEffect(() => {
    loadRange(currentMonth);
  }, [currentMonth, loadRange]);

  const monthStart = startOfMonth(currentMonth);
  const monthEnd = endOfMonth(currentMonth);
  const calStart = startOfWeek(monthStart, { weekStartsOn: 0 });
  const calEnd = endOfWeek(monthEnd, { weekStartsOn: 0 });
  const gridDays = eachDayOfInterval({ start: calStart, end: calEnd });

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

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Content Calendar</h1>
          <p className="mt-1 text-slate-500">Scheduled and published posts by day</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setCurrentMonth((m) => subMonths(m, 1))}
            className="rounded-lg border border-slate-200 bg-white p-2 text-slate-600 shadow-sm hover:bg-slate-50"
            aria-label="Previous month"
          >
            <ChevronLeft className="h-5 w-5" />
          </button>
          <span className="min-w-[10rem] text-center text-sm font-semibold text-slate-900">
            {format(currentMonth, "MMMM yyyy")}
          </span>
          <button
            type="button"
            onClick={() => setCurrentMonth((m) => addMonths(m, 1))}
            className="rounded-lg border border-slate-200 bg-white p-2 text-slate-600 shadow-sm hover:bg-slate-50"
            aria-label="Next month"
          >
            <ChevronRight className="h-5 w-5" />
          </button>
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
            const inMonth = isSameMonth(day, currentMonth);
            return (
              <div
                key={k}
                className={cn(
                  "min-h-[7.5rem] border-b border-r border-slate-100 p-1.5 last:border-r-0",
                  !inMonth && "bg-slate-50/80"
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
                      onClick={() => setSelected(item)}
                      className={cn(
                        "truncate rounded-md border px-1.5 py-0.5 text-left text-[10px] font-medium leading-tight transition-colors sm:text-xs",
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
