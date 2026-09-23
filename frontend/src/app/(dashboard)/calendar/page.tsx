"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  addDays,
  addMonths,
  addWeeks,
  endOfDay,
  format,
  isBefore,
  isSameDay,
  isSameMonth,
  isToday,
  isValid,
  parseISO,
  startOfDay,
  startOfMonth,
  startOfWeek,
} from "date-fns";
import { CalendarDays, ChevronLeft, ChevronRight, Lightbulb, ListChecks, Loader2, Plus, RefreshCw, Wand2 } from "lucide-react";
import { toast } from "sonner";
import { api, apiErrorCode, isGenerationQuotaError, postsApi, type SubscriptionInfo } from "@/lib/api";
import {
  isAbortError,
  postStudioApi,
  randomPostTime,
  type CalendarPost,
} from "@/lib/api-posts";
import { clientLabel, useActiveClient } from "@/lib/active-client";
import { trackFeature } from "@/lib/analytics";
import { publishUnavailableReason } from "@/lib/platforms";
import { cn } from "@/lib/utils";
import { Button, buttonVariants } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorBanner } from "@/components/ui/feedback";
import { Eyebrow, PageHeader, Panel } from "@/components/ui/panel";
import { SegmentedTabs } from "@/components/ui/tabs";
import { AddPostModal } from "@/components/posts/add-post-modal";
import { EventModal } from "@/components/posts/event-modal";
import { GeneratePostsModal } from "@/components/posts/generate-posts-modal";
import { QUEUE_PLATFORMS, platformLabel, platformTone } from "@/components/posts/platform";
import { ScheduleDialog } from "@/components/posts/schedule-dialog";

type View = "month" | "week";
type Scope = "client" | "all";

/*
 * Cadence's STATUS_COLOR, extended to this app's five statuses and matched to
 * StatusBadge so a colour means the same thing on both Posts screens.
 */
const STATUS_TONE: Record<string, { dot: string; border: string; label: string }> = {
  draft: { dot: "bg-amber-500", border: "border-l-amber-500", label: "Pending" },
  approved: { dot: "bg-blue-500", border: "border-l-blue-500", label: "Approved" },
  scheduled: { dot: "bg-violet-500", border: "border-l-violet-500", label: "Scheduled" },
  published: { dot: "bg-emerald-500", border: "border-l-emerald-500", label: "Published" },
  failed: { dot: "bg-red-500", border: "border-l-red-500", label: "Failed" },
};
const toneOf = (status: string) => STATUS_TONE[status] ?? STATUS_TONE.draft;

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function atOf(p: CalendarPost): Date | null {
  if (!p.scheduled_at) return null;
  const d = parseISO(p.scheduled_at);
  return isValid(d) ? d : null;
}

/** Monday-start week, like Cadence's computeWeekDays. */
function weekDays(anchor: Date): Date[] {
  const start = startOfWeek(anchor, { weekStartsOn: 1 });
  return Array.from({ length: 7 }, (_, i) => addDays(start, i));
}

/** 6×7 Sunday-start grid, like Cadence's computeMonthGrid. */
function monthCells(month: Date): Date[] {
  const start = startOfWeek(startOfMonth(month), { weekStartsOn: 0 });
  return Array.from({ length: 42 }, (_, i) => addDays(start, i));
}

function formatWeekRange(days: Date[]) {
  const [a, b] = [days[0], days[6]];
  return a.getMonth() === b.getMonth()
    ? `${format(a, "MMM d")} – ${format(b, "d, yyyy")}`
    : `${format(a, "MMM d")} – ${format(b, "MMM d, yyyy")}`;
}

// --- Week view pieces --------------------------------------------------------

function EventChip({
  event,
  delay,
  dragging,
  justMoved,
  onOpen,
  onDragStart,
  onDragEnd,
}: {
  event: CalendarPost;
  delay: number;
  dragging: boolean;
  justMoved: boolean;
  onOpen: () => void;
  onDragStart: (id: string) => void;
  onDragEnd: () => void;
}) {
  const tone = toneOf(event.status);
  const at = atOf(event);
  const blocked = publishUnavailableReason(event.platform);
  const draggable = event.status !== "published" && event.status !== "failed";
  return (
    <button
      type="button"
      onClick={onOpen}
      draggable={draggable}
      onDragStart={(e) => {
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/plain", event.id);
        onDragStart(event.id);
      }}
      onDragEnd={onDragEnd}
      title={blocked && event.status !== "draft" ? blocked : undefined}
      aria-label={`${platformLabel(event.platform)} · ${tone.label}${at ? ` · ${format(at, "HH:mm")}` : ""}: ${event.title || event.body}`}
      className={cn(
        "w-full rounded-md border border-l-[3px] border-line bg-panel/80 px-2 py-1.5 text-left backdrop-blur-xl transition-all duration-200 hover:-translate-y-px hover:bg-slate-500/5 motion-safe:animate-chip-in",
        tone.border,
        dragging && "opacity-35",
        justMoved && "border-emerald-500 ring-[3px] ring-emerald-500/20",
        draggable ? "cursor-grab active:cursor-grabbing" : "cursor-default"
      )}
      style={{ animationDelay: `${delay}s` }}
    >
      <div className="flex items-center gap-1.5">
        <span aria-hidden className={cn("h-1.5 w-1.5 rounded-full", platformTone(event.platform).dot)} />
        <span className="text-[10px] font-medium text-muted">{platformLabel(event.platform)}</span>
        {at && event.status === "scheduled" && (
          <span className="ml-auto font-mono text-[9px] text-violet-600">{format(at, "HH:mm")}</span>
        )}
      </div>
      <div className="mt-1 truncate text-[10.5px] text-slate-600">{event.title || event.body}</div>
    </button>
  );
}

function DayColumn({
  day,
  events,
  dragging,
  draggingStatus,
  flashId,
  addDisabled,
  onOpen,
  onAdd,
  onDragStart,
  onDragEnd,
  onDrop,
}: {
  day: Date;
  events: CalendarPost[];
  dragging: string | null;
  draggingStatus: string | null;
  flashId: string | null;
  addDisabled: string | null;
  onOpen: (e: CalendarPost) => void;
  onAdd: (day: Date) => void;
  onDragStart: (id: string) => void;
  onDragEnd: () => void;
  onDrop: (day: Date) => void;
}) {
  const [over, setOver] = useState(false);
  const today = isToday(day);
  const byStatus = events.reduce<Record<string, number>>((acc, e) => ({ ...acc, [e.status]: (acc[e.status] ?? 0) + 1 }), {});
  return (
    <div
      onDragOver={(e) => {
        if (dragging) {
          e.preventDefault();
          setOver(true);
        }
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e: DragEvent) => {
        e.preventDefault();
        setOver(false);
        onDrop(day);
      }}
      className={cn(
        "flex min-h-[220px] min-w-0 flex-col rounded-lg border backdrop-blur-xl transition-colors",
        over ? "border-accent" : today ? "border-accent/50" : "border-line",
        today ? "bg-accent/5 shadow-[0_8px_28px_rgb(var(--c-accent)/0.1)]" : "bg-panel/40"
      )}
    >
      <div className={cn("flex items-center justify-between border-b px-2.5 py-2", today ? "border-accent/40" : "border-line")}>
        <div>
          <div className="font-mono text-[9.5px] uppercase tracking-[0.08em] text-muted">{format(day, "EEE")}</div>
          <div className={cn("font-mono text-sm", today ? "text-accent-text" : "text-ink")}>{format(day, "d")}</div>
        </div>
        <button
          type="button"
          onClick={() => onAdd(day)}
          disabled={addDisabled !== null}
          aria-label={`Add a post on ${format(day, "EEE d")}`}
          title={addDisabled ?? undefined}
          className="press-scale text-muted hover:text-ink disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Plus className="h-3.5 w-3.5" />
        </button>
      </div>
      <div className="flex-1 space-y-1.5 p-1.5">
        {events.length === 0 && (
          <div className={cn("flex h-full items-center justify-center font-mono text-[9.5px]", over ? "text-accent-text" : "text-slate-400")}>
            {dragging ? (draggingStatus === "draft" ? "Approve first" : "Drop here") : "—"}
          </div>
        )}
        {events.map((e, i) => (
          <EventChip
            key={e.id}
            event={e}
            delay={i * 0.05}
            dragging={dragging === e.id}
            justMoved={flashId === e.id}
            onOpen={() => onOpen(e)}
            onDragStart={onDragStart}
            onDragEnd={onDragEnd}
          />
        ))}
      </div>
      {events.length > 0 && (
        <div
          className="flex gap-0.5 px-1.5 pb-1.5"
          title={Object.entries(byStatus)
            .map(([s, n]) => `${n} ${toneOf(s).label.toLowerCase()}`)
            .join(" · ")}
        >
          {Object.entries(byStatus).map(([s, n]) => (
            <div key={s} className={cn("h-[3px] rounded-full opacity-80", toneOf(s).dot)} style={{ flex: n }} />
          ))}
        </div>
      )}
    </div>
  );
}

// --- Page ----------------------------------------------------------------------

export default function CalendarPage() {
  const router = useRouter();
  const { active, activeId, clients, loading: clientsLoading, refresh: refreshClients } = useActiveClient();
  const [scope, setScope] = useState<Scope>("client");
  const [view, setView] = useState<View>("month");
  const [anchor, setAnchor] = useState(() => new Date());
  const [selectedDay, setSelectedDay] = useState(() => startOfDay(new Date()));

  const [entries, setEntries] = useState<CalendarPost[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => setTick((t) => t + 1), []);

  const [selected, setSelected] = useState<CalendarPost | null>(null);
  const [editBusy, setEditBusy] = useState(false);
  const [scheduleFor, setScheduleFor] = useState<{ post: CalendarPost; at: string | null } | null>(null);
  const [scheduleBusy, setScheduleBusy] = useState(false);
  const [addingDay, setAddingDay] = useState<Date | null>(null);
  const [addBusy, setAddBusy] = useState(false);
  const [dragging, setDragging] = useState<string | null>(null);
  const [flashId, setFlashId] = useState<string | null>(null);

  const [connected, setConnected] = useState<string[]>([]);
  const [supported, setSupported] = useState<string[]>(QUEUE_PLATFORMS.map((p) => p.id));
  const [sub, setSub] = useState<SubscriptionInfo | null>(null);
  const [fillOpen, setFillOpen] = useState(false);
  const [filling, setFilling] = useState<string | null>(null);
  const [fillError, setFillError] = useState<string | null>(null);
  const fillAbort = useRef<AbortController | null>(null);

  const clientId = scope === "client" ? activeId : null;
  const clientNames = useMemo(() => new Map(clients.map((c) => [c.id, clientLabel(c)])), [clients]);

  const days = useMemo(() => weekDays(anchor), [anchor]);
  const cells = useMemo(() => monthCells(anchor), [anchor]);
  const range = view === "month" ? cells : days;
  const headerLabel = view === "month" ? format(anchor, "MMMM yyyy") : formatWeekRange(days);
  const offCurrent = view === "month" ? !isSameMonth(anchor, new Date()) : !isSameDay(days[0], weekDays(new Date())[0]);

  const loadSub = useCallback(() => {
    api
      .getSubscription()
      .then(setSub)
      .catch(() => setSub(null));
  }, []);
  useEffect(loadSub, [loadSub]);

  useEffect(() => {
    setConnected([]);
    if (!activeId) return;
    let stale = false;
    postStudioApi
      .channels(activeId)
      .then((c) => {
        if (stale) return;
        setConnected(c.connected);
        setSupported(c.supported);
      })
      .catch(() => undefined);
    return () => {
      stale = true;
    };
  }, [activeId]);

  const seq = useRef(0);
  useEffect(() => {
    if (scope === "client" && !activeId) {
      setEntries([]);
      setLoading(clientsLoading);
      return;
    }
    const mine = ++seq.current;
    const start = startOfDay(range[0]).toISOString();
    const end = endOfDay(range[range.length - 1]).toISOString();
    setLoading(true);
    setLoadError(null);
    postStudioApi
      .calendar(start, end, clientId)
      .then((items) => mine === seq.current && setEntries(items))
      .catch((err) => {
        if (mine !== seq.current) return;
        setEntries([]);
        setLoadError(err instanceof Error ? err.message : "Could not load the calendar");
      })
      .finally(() => mine === seq.current && setLoading(false));
    // range is derived from anchor + view.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scope, clientId, activeId, clientsLoading, view, anchor, tick]);

  const eventsFor = useCallback(
    (day: Date) =>
      entries
        .filter((e) => {
          const at = atOf(e);
          return at !== null && isSameDay(at, day);
        })
        .sort((a, b) => (atOf(a)?.getTime() ?? 0) - (atOf(b)?.getTime() ?? 0)),
    [entries]
  );

  const used = sub?.generations_used ?? null;
  const limit = sub?.generations_limit ?? null;
  const remaining = used != null && limit != null ? Math.max(0, limit - used) : null;
  const atLimit = remaining === 0;
  const todayStart = startOfDay(new Date());
  const emptyUpcoming = range.filter(
    (d) => !isBefore(d, todayStart) && (view === "week" || isSameMonth(d, anchor)) && eventsFor(d).length === 0
  );

  const addDisabledReason = !active
    ? "Pick a client first"
    : connected.length === 0
      ? "Connect an account in Setup first"
      : null;
  const fillDisabledReason = !active
    ? "Pick a client first"
    : !active.has_brand_profile
      ? "Set up the brand profile first"
      : connected.length === 0
        ? "Connect at least one account first"
        : atLimit
          ? "No generations left this period"
          : emptyUpcoming.length === 0
            ? `No empty days left in this ${view}`
            : null;

  function flash(id: string) {
    setFlashId(id);
    setTimeout(() => setFlashId((cur) => (cur === id ? null : cur)), 1200);
  }

  function step(dir: 1 | -1) {
    setAnchor((a) => (view === "month" ? addMonths(a, dir) : addWeeks(a, dir)));
  }

  function goToday() {
    setAnchor(new Date());
    setSelectedDay(startOfDay(new Date()));
  }

  // --- Drag and drop (keyboard path: EventModal → Reschedule) ---

  async function dropOn(day: Date) {
    const post = entries.find((e) => e.id === dragging);
    setDragging(null);
    if (!post) return;
    if (post.status === "draft") {
      toast.info("Pending posts need approval before they can be scheduled.", {
        description: "Approve it in the Queue — moderation runs first — then drag it here.",
        action: { label: "Open Queue", onClick: () => router.push("/content") },
      });
      return;
    }
    if (post.status !== "approved" && post.status !== "scheduled") return;
    const blocked = publishUnavailableReason(post.platform);
    if (blocked) {
      toast.error(blocked);
      return;
    }
    const prev = atOf(post);
    const target = new Date(day);
    target.setHours(prev ? prev.getHours() : 10, prev ? prev.getMinutes() : 0, 0, 0);
    if (prev && prev.getTime() === target.getTime()) return;
    if (target.getTime() <= Date.now()) {
      toast.error("That time has already passed — drop it on a later day.");
      return;
    }
    if (post.status === "approved") {
      // First time it goes live: confirm the exact time (and the live-publish warning).
      setScheduleFor({ post, at: target.toISOString() });
      return;
    }
    try {
      await api.rescheduleContent(post.id, target.toISOString());
      setEntries((list) => list.map((e) => (e.id === post.id ? { ...e, scheduled_at: target.toISOString() } : e)));
      flash(post.id);
      toast.success(`Rescheduled to ${format(target, "EEE d MMM, HH:mm")}`);
      trackFeature("post-reschedule", { platform: post.platform, via: "drag" });
      reload();
    } catch (err) {
      toast.error(apiErrorCode(err) === "not_approved" ? "Approve this post first" : err instanceof Error ? err.message : "Could not reschedule");
      reload();
    }
  }

  async function confirmSchedule(iso: string) {
    if (!scheduleFor) return;
    const { post } = scheduleFor;
    setScheduleBusy(true);
    try {
      await api.scheduleContent(post.id, iso);
      setScheduleFor(null);
      setSelected(null);
      flash(post.id);
      toast.success(`${post.status === "scheduled" ? "Rescheduled" : "Scheduled"} for ${format(new Date(iso), "EEE d MMM, HH:mm")}`);
      trackFeature(post.status === "scheduled" ? "post-reschedule" : "post-schedule", { platform: post.platform });
      reload();
      void refreshClients();
    } catch (err) {
      const code = apiErrorCode(err);
      toast.error(
        code === "not_approved"
          ? "Approve this post first"
          : code === "platform_unavailable"
            ? "Scheduling isn't available for this platform yet."
            : code === "client_archived"
              ? "This client is archived."
              : err instanceof Error
                ? err.message
                : "Could not schedule"
      );
    } finally {
      setScheduleBusy(false);
    }
  }

  async function saveEdit(post: CalendarPost, body: string) {
    setEditBusy(true);
    try {
      const updated = await postsApi.edit(post.id, { body });
      if (post.status !== "draft" && updated.status === "draft") {
        toast.warning("Saved — back in Pending. Approve it again in the Queue before it can go out.");
      } else {
        toast.success("Changes saved");
      }
      setSelected(null);
      reload();
      void refreshClients();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not save changes");
    } finally {
      setEditBusy(false);
    }
  }

  async function addPost({ platform, body }: { platform: string; body: string }) {
    if (!addingDay || !activeId) return;
    setAddBusy(true);
    const at = new Date(addingDay);
    at.setHours(9, 0, 0, 0);
    try {
      await postStudioApi.createManual({ client_id: activeId, platform, body, planned_for: at.toISOString() });
      toast.success(`Added to ${format(at, "EEE d MMM")} as Pending`, {
        description: "Approve it in the Queue before it can be scheduled.",
      });
      trackFeature("calendar-add-post", { platform });
      setAddingDay(null);
      setSelectedDay(startOfDay(at));
      reload();
      void refreshClients();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not add the post");
    } finally {
      setAddBusy(false);
    }
  }

  // Cadence's "Fill {view} with AI": one Pending draft per chosen platform, each
  // planned on the next empty upcoming day. One generation each; never scheduled.
  async function runFill(platforms: string[], note: string) {
    if (!activeId) return;
    setFillOpen(false);
    setFillError(null);
    const slots = emptyUpcoming.slice(0, platforms.length);
    let made = 0;
    let cancelled = false;
    for (let i = 0; i < slots.length; i++) {
      const p = platforms[i];
      setFilling(p);
      const { hour, minute } = randomPostTime();
      const at = new Date(slots[i]);
      at.setHours(hour, minute, 0, 0);
      const controller = new AbortController();
      fillAbort.current = controller;
      try {
        await postStudioApi.generate(
          { client_id: activeId, platform: p, context_note: note || undefined, planned_for: at.toISOString() },
          controller.signal
        );
        made++;
      } catch (err) {
        if (isAbortError(err)) {
          cancelled = true;
          break;
        }
        setFillError(
          isGenerationQuotaError(err)
            ? "No generations left this period."
            : `Couldn't fill the ${view} — ${err instanceof Error ? err.message : "generation failed"}`
        );
        if (isGenerationQuotaError(err)) break;
      }
    }
    fillAbort.current = null;
    setFilling(null);
    loadSub();
    reload();
    void refreshClients();
    if (made) trackFeature("calendar-fill", { count: made, view });
    if (cancelled) toast(made ? `Stopped — ${made} draft${made === 1 ? "" : "s"} kept as Pending.` : "Cancelled — nothing was added.");
    else if (made)
      toast.success(`Added ${made} Pending draft${made === 1 ? "" : "s"} to empty days`, {
        description: "Each one still needs approval in the Queue, then a schedule.",
      });
    if (platforms.length > slots.length && !cancelled) {
      toast.info(`Only ${slots.length} empty day${slots.length === 1 ? "" : "s"} left — generated ${slots.length}.`);
    }
  }

  // --- Render ------------------------------------------------------------------

  const weekPosts = days.flatMap((d) => eventsFor(d));
  const count = (s: string) => weekPosts.filter((p) => p.status === s).length;
  const emptyWeekDays = days.filter((d) => eventsFor(d).length === 0);
  const draggingStatus = entries.find((e) => e.id === dragging)?.status ?? null;
  const selectedEvents = eventsFor(selectedDay);
  const noClient = !clientsLoading && !activeId;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Posts"
        title="Content Calendar"
        description="Every planned, scheduled and published post by day. Drag an approved or scheduled post to another day to reschedule it — the time of day is kept."
        actions={
          <>
            <SegmentedTabs
              label="Calendar scope"
              items={[
                { id: "client" as Scope, label: clientLabel(active) },
                { id: "all" as Scope, label: "All clients" },
              ]}
              value={scope}
              onChange={setScope}
            />
            <Link href="/content" className={buttonVariants({ variant: "secondary", size: "sm" })}>
              <ListChecks className="h-3.5 w-3.5" /> Queue
            </Link>
          </>
        }
      />

      {noClient ? (
        <EmptyState
          icon={CalendarDays}
          title="Add a client first"
          description="The calendar shows a client's planned and scheduled posts."
          action={
            <Link href="/clients?new=1" className={buttonVariants({ size: "sm" })}>
              Add a client
            </Link>
          }
        />
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <button
                type="button"
                aria-label={view === "month" ? "Previous month" : "Previous week"}
                onClick={() => step(-1)}
                className="press-scale text-muted hover:text-ink"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              <h2 className="min-w-[150px] font-display text-[17px] text-ink" aria-live="polite">
                {headerLabel}
              </h2>
              <button
                type="button"
                aria-label={view === "month" ? "Next month" : "Next week"}
                onClick={() => step(1)}
                className="press-scale text-muted hover:text-ink"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
              {offCurrent && (
                <button
                  type="button"
                  onClick={goToday}
                  className="press-scale rounded-md border border-accent/40 px-2 py-1 text-[11px] font-medium text-accent-text"
                >
                  Today
                </button>
              )}
              {loading && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted" aria-label="Loading" />}
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <SegmentedTabs
                label="Calendar view"
                items={[
                  { id: "month" as View, label: "Month" },
                  { id: "week" as View, label: "Week" },
                ]}
                value={view}
                onChange={setView}
              />
              <Button
                onClick={() => setFillOpen(true)}
                disabled={filling !== null || fillDisabledReason !== null}
                title={fillDisabledReason ?? undefined}
              >
                {filling ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Wand2 className="h-3.5 w-3.5" />}
                {filling ? `Writing for ${platformLabel(filling)}…` : `Fill ${view} with AI`}
              </Button>
              {filling && (
                <button
                  type="button"
                  onClick={() => fillAbort.current?.abort()}
                  className="font-mono text-[11px] text-muted underline hover:text-ink"
                >
                  Cancel
                </button>
              )}
            </div>
          </div>

          {view === "week" && (
            <p className="-mt-3 text-[11px] text-muted">
              Drag an approved or scheduled post to a different day to reschedule it. Pending posts need approval first;
              every post also has a keyboard Reschedule in its details.
            </p>
          )}
          {active && !active.has_brand_profile ? (
            <ErrorBanner
              message="Set up this client's brand profile before generating posts."
              onRetry={() => router.push("/setup/profile")}
              retryLabel="Go to Profile"
            />
          ) : active && connected.length === 0 ? (
            <ErrorBanner
              message="Connect at least one account before adding or generating posts here."
              onRetry={() => router.push("/setup/accounts")}
              retryLabel="Go to Setup"
            />
          ) : atLimit ? (
            <ErrorBanner message={`You've used all ${limit} generations this period. Upgrade under Settings › Billing to keep going.`} />
          ) : fillError ? (
            <ErrorBanner message={fillError} onRetry={() => setFillOpen(true)} />
          ) : null}
          {loadError && <ErrorBanner message={loadError} onRetry={reload} />}

          {view === "month" ? (
            <div className="motion-safe:animate-screen-in">
              <div className="overflow-x-auto">
                <div className="grid min-w-[770px] grid-cols-7 gap-px overflow-hidden rounded-xl border border-line bg-line">
                  {WEEKDAYS.map((d) => (
                    <div key={d} className="bg-panel py-2 text-center text-[10px] font-medium uppercase tracking-wider text-muted">
                      {d}
                    </div>
                  ))}
                  {cells.map((c) => {
                    const dayEvents = eventsFor(c);
                    const other = !isSameMonth(c, anchor);
                    const sel = isSameDay(c, selectedDay);
                    const today = isToday(c);
                    return (
                      <button
                        key={c.toISOString()}
                        type="button"
                        onClick={() => setSelectedDay(startOfDay(c))}
                        onDragOver={(e) => {
                          if (dragging) e.preventDefault();
                        }}
                        onDrop={(e) => {
                          e.preventDefault();
                          void dropOn(c);
                        }}
                        aria-pressed={sel}
                        aria-label={`${format(c, "MMMM d")}${dayEvents.length ? `, ${dayEvents.length} post${dayEvents.length === 1 ? "" : "s"}` : ""}`}
                        className={cn(
                          "press-scale min-h-[82px] p-2 text-left",
                          today ? "bg-accent/5" : "bg-panel",
                          sel ? "ring-[1.5px] ring-inset ring-sky-500" : today && "shadow-[inset_0_0_0_1px_rgb(var(--c-accent)/0.35)]",
                          other && "opacity-35"
                        )}
                      >
                        <div className={cn("mb-1 font-display text-[12.5px]", today ? "font-semibold text-accent-text" : "text-slate-600")}>
                          {format(c, "d")}
                        </div>
                        <div className="flex flex-wrap gap-1">
                          {dayEvents.slice(0, 4).map((e) => (
                            <span key={e.id} className={cn("h-1.5 w-1.5 rounded-full", toneOf(e.status).dot, flashId === e.id && "animate-pop-in")} />
                          ))}
                        </div>
                        {dayEvents.length > 4 && (
                          <div className="mt-1 font-mono text-[9px] text-muted">+{dayEvents.length - 4} more</div>
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Selected-day agenda. Rows drag onto any cell above. */}
              <Panel dashed className="mt-4 p-5">
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="font-display text-sm text-ink">{format(selectedDay, "MMMM d, yyyy")}</h3>
                  <button
                    type="button"
                    onClick={() => setAddingDay(selectedDay)}
                    disabled={addDisabledReason !== null || isBefore(selectedDay, todayStart)}
                    title={addDisabledReason ?? (isBefore(selectedDay, todayStart) ? "Can't plan a post in the past" : undefined)}
                    className="press-scale flex items-center gap-1 text-[11.5px] font-medium text-accent-text disabled:cursor-not-allowed disabled:text-muted disabled:opacity-50"
                  >
                    <Plus className="h-3.5 w-3.5" /> Add post
                  </button>
                </div>
                {selectedEvents.length === 0 ? (
                  <p className="text-[12.5px] text-muted">Nothing planned this day yet.</p>
                ) : (
                  <div className="space-y-2">
                    {selectedEvents.map((e) => {
                      const at = atOf(e);
                      const draggable = e.status !== "published" && e.status !== "failed";
                      return (
                        <button
                          key={e.id}
                          type="button"
                          onClick={() => setSelected(e)}
                          draggable={draggable}
                          onDragStart={(ev) => {
                            ev.dataTransfer.effectAllowed = "move";
                            ev.dataTransfer.setData("text/plain", e.id);
                            setDragging(e.id);
                          }}
                          onDragEnd={() => setDragging(null)}
                          className={cn(
                            "press-scale flex w-full items-center gap-3 rounded-lg border border-line bg-panel/80 px-3 py-2.5 text-left motion-safe:animate-chip-in",
                            flashId === e.id && "border-emerald-500",
                            draggable && "cursor-grab"
                          )}
                        >
                          <span className={cn("h-[7px] w-[7px] shrink-0 rounded-full", toneOf(e.status).dot)} aria-hidden />
                          <span className="w-[90px] shrink-0 text-[12.5px] font-medium text-ink">{platformLabel(e.platform)}</span>
                          <span className="flex-1 truncate text-xs text-slate-600">{e.title || e.body}</span>
                          {scope === "all" && (
                            <span className="hidden shrink-0 text-[11px] text-muted sm:inline">{clientNames.get(e.client_id)}</span>
                          )}
                          <span className="shrink-0 font-mono text-[10px] text-muted">{toneOf(e.status).label}</span>
                          {at && <span className="shrink-0 font-mono text-[10.5px] text-muted">{format(at, "h:mm a")}</span>}
                        </button>
                      );
                    })}
                  </div>
                )}
              </Panel>
            </div>
          ) : (
            <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_260px]">
              <div className="min-w-0">
                {weekPosts.length > 0 && (
                  <div className="mb-3 flex flex-wrap items-center gap-4 px-1">
                    <div className="flex h-1.5 min-w-[120px] flex-1 overflow-hidden rounded-full bg-slate-500/10">
                      {(["draft", "approved", "scheduled", "published", "failed"] as const).map((s) =>
                        count(s) > 0 ? (
                          <div
                            key={s}
                            className={cn("transition-[width] duration-500", toneOf(s).dot)}
                            style={{ width: `${(count(s) / weekPosts.length) * 100}%` }}
                            title={`${count(s)} ${toneOf(s).label.toLowerCase()}`}
                          />
                        ) : null
                      )}
                    </div>
                    <div className="flex shrink-0 flex-wrap items-center gap-3 text-[11px] font-medium">
                      {count("draft") > 0 && <span className="text-amber-700">{count("draft")} to review</span>}
                      {count("approved") > 0 && <span className="text-blue-600">{count("approved")} to schedule</span>}
                      {count("scheduled") > 0 && <span className="text-violet-600">{count("scheduled")} scheduled</span>}
                      {count("published") > 0 && <span className="text-emerald-600">{count("published")} published</span>}
                      {emptyWeekDays.length > 0 && (
                        <span className="font-normal text-muted">
                          {emptyWeekDays.length} empty day{emptyWeekDays.length === 1 ? "" : "s"}
                        </span>
                      )}
                    </div>
                  </div>
                )}
                <div className="overflow-x-auto">
                  <div className="grid min-w-[1120px] grid-cols-7 gap-2 lg:min-w-0">
                    {days.map((d) => (
                      <DayColumn
                        key={d.toISOString()}
                        day={d}
                        events={eventsFor(d)}
                        dragging={dragging}
                        draggingStatus={draggingStatus}
                        flashId={flashId}
                        addDisabled={addDisabledReason ?? (isBefore(d, todayStart) ? "Can't plan a post in the past" : null)}
                        onOpen={setSelected}
                        onAdd={setAddingDay}
                        onDragStart={setDragging}
                        onDragEnd={() => setDragging(null)}
                        onDrop={(day) => void dropOn(day)}
                      />
                    ))}
                  </div>
                </div>
              </div>

              {/* Cadence's "Weekly strategy" panel, from real data: its themes were
                  hard-coded, so this shows what is actually planned instead. */}
              <Panel dashed className="self-start p-5 motion-safe:animate-screen-in">
                <div className="flex items-center gap-1.5">
                  <Lightbulb className="h-3.5 w-3.5 text-accent-text motion-safe:animate-breathe" aria-hidden />
                  <Eyebrow>This week</Eyebrow>
                </div>
                <p className="mt-2 font-mono text-[11px] leading-relaxed text-muted">
                  What&apos;s actually planned — from the queue, not a template.
                </p>
                <div className="mt-4 space-y-4">
                  <div className="border-l-2 border-line pl-3">
                    <div className="font-mono text-[10px] tracking-wider text-accent-text">CAMPAIGN FOCUS</div>
                    {scope === "client" && active?.campaign_focus ? (
                      <div className="mt-0.5 text-[12.5px] text-ink">{active.campaign_focus}</div>
                    ) : (
                      <div className="mt-0.5 text-[12px] text-muted">
                        {scope === "all" ? "Varies by client." : "None set — "}
                        {scope === "client" && (
                          <Link href="/setup/profile#campaign" className="text-accent-text underline">
                            set one
                          </Link>
                        )}
                      </div>
                    )}
                  </div>
                  <div className="border-l-2 border-line pl-3">
                    <div className="font-mono text-[10px] tracking-wider text-accent-text">NEEDS YOU</div>
                    <div className="mt-0.5 text-[12.5px] text-ink">
                      {count("draft")} to review · {count("approved")} to schedule
                    </div>
                    {count("draft") > 0 && (
                      <Link href="/content" className="font-mono text-[10px] text-muted underline">
                        Review in the Queue →
                      </Link>
                    )}
                  </div>
                  <div className="border-l-2 border-line pl-3">
                    <div className="font-mono text-[10px] tracking-wider text-accent-text">EMPTY DAYS</div>
                    {emptyWeekDays.length === 0 ? (
                      <div className="mt-0.5 text-[12.5px] text-ink">Every day has something planned.</div>
                    ) : (
                      <div className="mt-1 flex flex-wrap gap-1.5">
                        {emptyWeekDays.map((d) => {
                          const past = isBefore(d, todayStart);
                          return (
                            <button
                              key={d.toISOString()}
                              type="button"
                              disabled={past || addDisabledReason !== null}
                              onClick={() => setAddingDay(d)}
                              title={past ? "In the past" : addDisabledReason ?? `Add a post on ${format(d, "EEE d")}`}
                              className="rounded-md border border-line px-2 py-0.5 font-mono text-[10.5px] text-muted hover:text-ink disabled:opacity-40"
                            >
                              {format(d, "EEE d")}
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </div>
              </Panel>
            </div>
          )}

          <div className="flex flex-wrap items-center gap-5">
            {Object.entries(STATUS_TONE).map(([s, t]) => (
              <div key={s} className="flex items-center gap-1.5">
                <span className={cn("h-2 w-2", t.dot)} />
                <span className="font-mono text-[10.5px] text-muted">{t.label}</span>
              </div>
            ))}
            {loadError === null && !loading && entries.length === 0 && (
              <span className="flex items-center gap-1 font-mono text-[10.5px] text-muted">
                <RefreshCw className="h-3 w-3" /> Nothing planned in this {view} yet.
              </span>
            )}
          </div>
        </>
      )}

      <EventModal
        event={selected}
        clientName={selected && scope === "all" ? clientNames.get(selected.client_id) ?? null : null}
        busy={editBusy}
        onClose={() => setSelected(null)}
        onEdit={(e, body) => void saveEdit(e, body)}
        onReschedule={(e) => setScheduleFor({ post: e, at: e.scheduled_at })}
      />

      <ScheduleDialog
        open={scheduleFor !== null}
        mode={scheduleFor?.post.status === "scheduled" ? "reschedule" : "schedule"}
        platform={scheduleFor?.post.platform ?? ""}
        clientName={scheduleFor ? clientNames.get(scheduleFor.post.client_id) ?? null : null}
        currentAt={scheduleFor?.at}
        busy={scheduleBusy}
        onClose={() => setScheduleFor(null)}
        onConfirm={(iso) => void confirmSchedule(iso)}
      />

      <AddPostModal
        day={addingDay}
        platforms={supported}
        connected={connected}
        busy={addBusy}
        onClose={() => setAddingDay(null)}
        onAdd={(d) => void addPost(d)}
      />

      <GeneratePostsModal
        open={fillOpen}
        platforms={connected}
        remaining={remaining}
        title={`Fill ${view} with AI — choose platforms`}
        footnote={`${emptyUpcoming.length} empty upcoming day${emptyUpcoming.length === 1 ? "" : "s"} in this ${view} — one Pending draft per day, each with a planned time. Nothing is scheduled until you approve and schedule it.`}
        onCancel={() => setFillOpen(false)}
        onConfirm={(p, note) => void runFill(p, note)}
      />
    </div>
  );
}
