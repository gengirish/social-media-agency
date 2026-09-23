"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { format } from "date-fns";
import { toast } from "sonner";
import {
  CalendarDays,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  FileText,
  Inbox,
  Layers,
  ListChecks,
  Loader2,
  RefreshCw,
  Send,
  TrendingUp,
  Wand2,
  X,
} from "lucide-react";
import {
  api,
  apiErrorCode,
  isGenerationQuotaError,
  moderationIssues,
  postsApi,
  type ModerationIssue,
  type QueuePost,
  type QueueStatus,
  type SavedBrandProfile,
  type SubscriptionInfo,
} from "@/lib/api";
import { downloadTextFile, isAbortError, postStudioApi } from "@/lib/api-posts";
import { clientLabel, useActiveClient } from "@/lib/active-client";
import { trackFeature } from "@/lib/analytics";
import { canPublish, publishUnavailableReason } from "@/lib/platforms";
import { Button, buttonVariants } from "@/components/ui/button";
import { CampaignIndicator } from "@/components/ui/campaign-indicator";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorBanner, undoToast } from "@/components/ui/feedback";
import { Eyebrow, PageHeader, Panel } from "@/components/ui/panel";
import { PlatformFilterRow } from "@/components/ui/platform-filter";
import { QuotaHint } from "@/components/ui/quota-hint";
import { SearchInput } from "@/components/ui/search-input";
import { SegmentedTabs } from "@/components/ui/tabs";
import { statusLabel } from "@/components/ui/status-badge";
import { cn } from "@/lib/utils";
import { PostDialog } from "@/components/posts/dialog";
import { GeneratePostsModal } from "@/components/posts/generate-posts-modal";
import { ModerationWarning } from "@/components/posts/moderation-warning";
import { PostCard, type PostAction, type PostEdit } from "@/components/posts/post-card";
import { PublishConfirm } from "@/components/posts/publish-confirm";
import { QUEUE_PLATFORMS, platformLabel } from "@/components/posts/platform";
import { QUEUE_TABS, QueueTabs } from "@/components/posts/queue-tabs";
import { AccountChip, ClientProfileCard, MiniStat, UsageMeter } from "@/components/posts/queue-sidebar";
import { ScheduleDialog } from "@/components/posts/schedule-dialog";

const PER_PAGE = 50;

const EMPTY: Record<QueueStatus, { title: string; body: string }> = {
  draft: {
    title: "Queue is empty — generate your first post above",
    body: "Posts from Generate, campaigns and Amplify land here as Pending. Each one needs a person to approve it — after a moderation check — before it can be scheduled or published.",
  },
  approved: {
    title: "No approved posts",
    body: "Approve a Pending post and it moves here, ready to schedule or publish.",
  },
  scheduled: {
    title: "Nothing scheduled",
    body: "Schedule an approved post and it appears here and on the Calendar until it goes out.",
  },
  published: {
    title: "Nothing published yet",
    body: "Posts show up here once they have gone out to a connected account.",
  },
  failed: {
    title: "No failed posts",
    body: "If a platform rejects a publish, the post and the reason it gave will show up here.",
  },
};

type Counts = Partial<Record<QueueStatus, number | null>>;
type Scope = "client" | "all";
interface RunResult {
  platform: string;
  ok: boolean;
  preview?: string;
  error?: string;
}
interface RunSummary {
  startedAt: string;
  note: string;
  results: RunResult[];
}

function addAll(set: Set<string>, ids: string[]) {
  const next = new Set(set);
  ids.forEach((id) => next.add(id));
  return next;
}
function removeAll(set: Set<string>, ids: string[]) {
  const next = new Set(set);
  ids.forEach((id) => next.delete(id));
  return next;
}

export default function QueuePage() {
  const { active, activeId, clients, loading: clientsLoading, refresh: refreshClients } = useActiveClient();

  const [scope, setScope] = useState<Scope>("client");
  const [tab, setTab] = useState<QueueStatus>("draft");
  const [platform, setPlatform] = useState("all");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [reloadTick, setReloadTick] = useState(0);
  const reload = useCallback(() => setReloadTick((t) => t + 1), []);

  const [items, setItems] = useState<QueuePost[]>([]);
  const [total, setTotal] = useState(0);
  const [counts, setCounts] = useState<Counts>({});
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [busy, setBusy] = useState<Record<string, PostAction>>({});
  const [editingId, setEditingId] = useState<string | null>(null);
  const [moderation, setModeration] = useState<{ post: QueuePost; issues: ModerationIssue[] } | null>(null);
  const [scheduleFor, setScheduleFor] = useState<QueuePost | null>(null);
  const [publishFor, setPublishFor] = useState<QueuePost | null>(null);
  const [now, setNow] = useState(() => Date.now());

  const [removing, setRemoving] = useState<Set<string>>(new Set());
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkBusy, setBulkBusy] = useState<null | "approve" | "publish">(null);
  const [bulkPublishOpen, setBulkPublishOpen] = useState(false);

  const [channels, setChannels] = useState<{ connected: string[]; supported: string[] } | null>(null);
  const [profile, setProfile] = useState<SavedBrandProfile | null>(null);
  const [sub, setSub] = useState<SubscriptionInfo | null>(null);

  const [genModalOpen, setGenModalOpen] = useState(false);
  const [generating, setGenerating] = useState<string | null>(null);
  const [genError, setGenError] = useState<string | null>(null);
  const [runSummary, setRunSummary] = useState<RunSummary | null>(null);
  const genAbort = useRef<AbortController | null>(null);
  const regenAbort = useRef<AbortController | null>(null);
  const briefAbort = useRef<AbortController | null>(null);

  const clientId = scope === "client" ? activeId : null;
  const clientNames = useMemo(() => new Map(clients.map((c) => [c.id, clientLabel(c)])), [clients]);

  // Overdue labels depend on the clock, not just on data.
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 60_000);
    return () => clearInterval(t);
  }, []);

  const loadSub = useCallback(() => {
    api
      .getSubscription()
      .then(setSub)
      .catch(() => setSub(null));
  }, []);
  useEffect(loadSub, [loadSub]);

  // The active client's channels and brand profile (sidebar + generate gating).
  useEffect(() => {
    setChannels(null);
    setProfile(null);
    if (!activeId) return;
    let stale = false;
    postStudioApi
      .channels(activeId)
      .then((c) => !stale && setChannels(c))
      .catch(() => !stale && setChannels({ connected: [], supported: QUEUE_PLATFORMS.map((p) => p.id) }));
    api
      .getBrandProfile(activeId)
      .then((p) => !stale && setProfile(p))
      .catch(() => !stale && setProfile(null));
    return () => {
      stale = true;
    };
  }, [activeId]);

  // A newer request supersedes an older one; stale responses are dropped.
  const loadSeq = useRef(0);
  useEffect(() => {
    if (scope === "client" && !activeId) {
      setItems([]);
      setTotal(0);
      setCounts({});
      setLoading(clientsLoading);
      return;
    }
    const seq = ++loadSeq.current;
    const filters = { client_id: clientId ?? undefined, platform: platform === "all" ? undefined : platform };
    setLoading(true);
    setLoadError(null);
    const countsP = Promise.all(
      QUEUE_TABS.map(({ status }) =>
        postsApi
          .count(status, filters)
          .then((n) => [status, n] as const)
          .catch(() => [status, null] as const)
      )
    );
    postsApi
      .list({ ...filters, content_status: tab, page, per_page: PER_PAGE })
      .then((res) => {
        if (seq !== loadSeq.current) return;
        setItems(res.items);
        setTotal(res.total);
        setHidden(new Set());
      })
      .catch((err) => {
        if (seq !== loadSeq.current) return;
        setItems([]);
        setTotal(0);
        setLoadError(err instanceof Error ? err.message : "Could not load posts");
      })
      .finally(() => {
        if (seq === loadSeq.current) setLoading(false);
      });
    void countsP.then((c) => {
      if (seq === loadSeq.current) setCounts(Object.fromEntries(c));
    });
  }, [scope, clientId, activeId, clientsLoading, tab, platform, page, reloadTick]);

  // Selection is per tab, as in Cadence.
  useEffect(() => setSelectedIds(new Set()), [tab, scope, clientId, platform]);

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    return items.filter((p) => {
      if (hidden.has(p.id)) return false;
      if (!q) return true;
      return [p.title, p.body, ...(p.hashtags ?? []), clientNames.get(p.client_id) ?? ""].some((s) =>
        (s ?? "").toLowerCase().includes(q)
      );
    });
  }, [items, search, clientNames, hidden]);

  const connected = useMemo(() => channels?.connected ?? [], [channels]);
  const filterPlatforms = useMemo(() => {
    if (scope === "all") return QUEUE_PLATFORMS.map((p) => p.id as string);
    const seen = items.map((p) => p.platform?.toLowerCase()).filter(Boolean);
    return Array.from(new Set([...connected, ...seen]));
  }, [scope, connected, items]);
  // Drafting touches no platform API, so with nothing connected every supported
  // platform is offered (Cadence) — publishing still needs a connection.
  const pickable = useMemo(
    () =>
      connected.length > 0 ? connected.filter((p) => channels?.supported.includes(p)) : channels?.supported ?? [],
    [connected, channels]
  );

  const used = sub?.generations_used ?? null;
  const limit = sub?.generations_limit ?? null;
  const remaining = used != null && limit != null ? Math.max(0, limit - used) : null;
  const atLimit = remaining === 0;

  function setPostBusy(id: string, action: PostAction | null) {
    setBusy((prev) => {
      const next = { ...prev };
      if (action) next[id] = action;
      else delete next[id];
      return next;
    });
  }

  function replaceItem(updated: QueuePost) {
    setItems((prev) =>
      prev
        .map((p) => (p.id === updated.id ? { ...p, ...updated } : p))
        // A post whose status changed leaves this tab (e.g. an edit sent it back to Pending).
        .filter((p) => p.id !== updated.id || p.status === tab)
    );
  }

  function changeTab(status: QueueStatus) {
    setTab(status);
    setPage(1);
    setEditingId(null);
  }

  function gateError(err: unknown, fallback: string) {
    const code = apiErrorCode(err);
    if (code === "not_approved") {
      toast.error("Approve this post first");
      reload();
    } else if (code === "client_archived") {
      toast.error("This client is archived. Restore it from Setup › Clients to post for it.");
    } else if (code === "platform_unavailable") {
      toast.error("Scheduling isn't available for this platform yet.");
    } else {
      toast.error(err instanceof Error ? err.message : fallback);
    }
  }

  // --- Single-post actions (latest closures, stable wrappers for the memoized card) ---

  async function approve(post: QueuePost, override = false) {
    setPostBusy(post.id, "approve");
    try {
      const res = await postsApi.approve(post.id, override);
      setModeration(null);
      const mod = res.moderation?.status;
      if (mod === "unavailable") toast.warning("Moderation check unavailable — approved without it");
      else if (override || mod === "overridden") toast.success("Approved — moderation override recorded");
      else toast.success("Approved");
      trackFeature("post-approve", { platform: post.platform, override });
      reload();
      void refreshClients();
      // Cadence's "Approve & schedule": the picker opens straight after a passed check.
      if (canPublish(post.platform)) setScheduleFor({ ...post, status: "approved" });
    } catch (err) {
      const code = apiErrorCode(err);
      if (code === "moderation_flagged") {
        setModeration({ post, issues: moderationIssues(err) });
      } else if (code === "invalid_status") {
        setModeration(null);
        toast.error("This post is no longer Pending — refreshed the queue");
        reload();
      } else {
        toast.error(err instanceof Error ? err.message : "Approve failed");
      }
    } finally {
      setPostBusy(post.id, null);
    }
  }

  async function saveEdit(post: QueuePost, edit: PostEdit) {
    try {
      const updated = await postsApi.edit(post.id, edit);
      const merged = { ...post, ...updated } as QueuePost;
      if (post.status !== "draft" && updated.status === "draft") {
        toast.warning(`Saved — back in Pending. Approve it again${post.status === "scheduled" ? ", then reschedule" : ""}.`);
        setEditingId(null);
        void refreshClients();
        reload();
      }
      replaceItem(merged);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not save changes");
      throw err;
    }
  }

  async function schedule(post: QueuePost, iso: string) {
    const rescheduling = post.status === "scheduled";
    setPostBusy(post.id, "schedule");
    try {
      await api.scheduleContent(post.id, iso);
      setScheduleFor(null);
      toast.success(`${rescheduling ? "Rescheduled" : "Scheduled"} for ${format(new Date(iso), "EEE d MMM, HH:mm")}`);
      trackFeature(rescheduling ? "post-reschedule" : "post-schedule", { platform: post.platform });
      reload();
      void refreshClients();
    } catch (err) {
      gateError(err, "Could not schedule");
    } finally {
      setPostBusy(post.id, null);
    }
  }

  async function publish(post: QueuePost) {
    setPostBusy(post.id, "publish");
    try {
      const res = await api.publishContent(post.id);
      setPublishFor(null);
      trackFeature("content-publish", { platform: post.platform });
      if (res?.url) {
        const url = res.url;
        toast.success("Published", { action: { label: "View", onClick: () => window.open(url, "_blank", "noopener") } });
      } else {
        toast.success("Publish request accepted");
      }
    } catch (err) {
      setPublishFor(null);
      gateError(err, "Publish failed");
    } finally {
      setPostBusy(post.id, null);
      reload();
      void refreshClients();
    }
  }

  function deletePosts(posts: QueuePost[]) {
    const ids = posts.map((p) => p.id);
    if (!ids.length) return;
    setSelectedIds((prev) => removeAll(prev, ids));
    setRemoving((prev) => addAll(prev, ids));
    setTimeout(() => {
      setHidden((prev) => addAll(prev, ids));
      setRemoving((prev) => removeAll(prev, ids));
    }, 320);
    const first = posts[0];
    const message =
      posts.length > 1
        ? `${posts.length} posts deleted.`
        : `${platformLabel(first.platform)} ${statusLabel(first.status).toLowerCase()} post deleted${
            first.status === "scheduled" ? " — it won't publish" : ""
          }.`;
    undoToast(
      message,
      () => setHidden((prev) => removeAll(prev, ids)),
      async () => {
        const results = await Promise.allSettled(ids.map((id) => postStudioApi.remove(id)));
        const failed = ids.filter((_, i) => results[i].status === "rejected");
        if (failed.length) {
          setHidden((prev) => removeAll(prev, failed));
          toast.error(`Couldn't delete ${failed.length === 1 ? "a post" : `${failed.length} posts`} — ${failed.length === 1 ? "it's" : "they're"} back in the list.`);
        } else {
          trackFeature("post-delete", { count: ids.length });
        }
        reload();
        void refreshClients();
      }
    );
  }

  async function regenerate(post: QueuePost) {
    if (atLimit) {
      toast.error("No generations left this period — upgrade under Settings › Billing.");
      return;
    }
    const controller = new AbortController();
    regenAbort.current = controller;
    setPostBusy(post.id, "regenerate");
    try {
      const updated = await postStudioApi.regenerate(post.id, controller.signal);
      replaceItem(updated);
      trackFeature("post-regenerate", { platform: post.platform });
      loadSub();
    } catch (err) {
      if (isAbortError(err)) toast("Cancelled — the draft is unchanged.");
      else if (isGenerationQuotaError(err)) {
        toast.error("No generations left this period.");
        loadSub();
      } else if (apiErrorCode(err) === "invalid_status") {
        toast.error("Only Pending posts can be regenerated — refreshed the queue.");
        reload();
      } else toast.error(err instanceof Error ? err.message : "Couldn't rewrite this post — try again.");
    } finally {
      regenAbort.current = null;
      setPostBusy(post.id, null);
    }
  }

  async function requestBrief(post: QueuePost) {
    const controller = new AbortController();
    briefAbort.current = controller;
    setPostBusy(post.id, "brief");
    try {
      const updated = await postStudioApi.creativeBrief(post.id, controller.signal);
      replaceItem(updated);
      toast.success("Creative brief ready — open it on the card.");
      trackFeature("creative-brief", { platform: post.platform });
      loadSub();
    } catch (err) {
      if (isAbortError(err)) toast("Cancelled — no brief was added.");
      else if (isGenerationQuotaError(err)) {
        toast.error("No generations left this period.");
        loadSub();
      } else toast.error(err instanceof Error ? err.message : "Couldn't write a brief — try again.");
    } finally {
      briefAbort.current = null;
      setPostBusy(post.id, null);
    }
  }

  const latest = useRef({ approve, saveEdit, deletePosts, regenerate, requestBrief });
  latest.current = { approve, saveEdit, deletePosts, regenerate, requestBrief };
  const onApprove = useCallback((p: QueuePost) => void latest.current.approve(p), []);
  const onEditSave = useCallback((p: QueuePost, e: PostEdit) => latest.current.saveEdit(p, e), []);
  const onDelete = useCallback((p: QueuePost) => latest.current.deletePosts([p]), []);
  const onRegenerate = useCallback((p: QueuePost) => void latest.current.regenerate(p), []);
  const onRequestBrief = useCallback((p: QueuePost) => void latest.current.requestBrief(p), []);
  const onCancelRegenerate = useCallback(() => regenAbort.current?.abort(), []);
  const onCancelBrief = useCallback(() => briefAbort.current?.abort(), []);
  const onEditStart = useCallback((id: string) => setEditingId(id), []);
  const onEditClose = useCallback(() => setEditingId(null), []);
  const onSchedule = useCallback((p: QueuePost) => setScheduleFor(p), []);
  const onPublish = useCallback((p: QueuePost) => setPublishFor(p), []);
  const onToggleSelect = useCallback(
    (id: string) =>
      setSelectedIds((prev) => {
        const next = new Set(prev);
        if (next.has(id)) next.delete(id);
        else next.add(id);
        return next;
      }),
    []
  );

  // --- Generate a post (batch, one generation each, stops at the quota) ---

  async function runGeneration(platforms: string[], note: string) {
    if (!activeId || generating || !platforms.length) return;
    setGenModalOpen(false);
    setGenError(null);
    setRunSummary(null);
    changeTab("draft");
    const startedAt = new Date().toISOString();
    const results: RunResult[] = [];
    let cancelled = false;
    for (const p of platforms) {
      setGenerating(p);
      const controller = new AbortController();
      genAbort.current = controller;
      try {
        const piece = await postStudioApi.generate(
          { client_id: activeId, platform: p, context_note: note || undefined },
          controller.signal
        );
        results.push({ platform: p, ok: true, preview: piece.body.slice(0, 140) });
      } catch (err) {
        if (isAbortError(err)) {
          cancelled = true;
          break;
        }
        results.push({ platform: p, ok: false, error: err instanceof Error ? err.message : "failed" });
        if (isGenerationQuotaError(err)) break;
      }
    }
    genAbort.current = null;
    setGenerating(null);
    loadSub();
    reload();
    void refreshClients();
    const ok = results.filter((r) => r.ok).length;
    if (ok) trackFeature("post-generate", { count: ok, with_note: Boolean(note) });
    if (cancelled) {
      toast(ok ? `Stopped — ${ok} draft${ok === 1 ? "" : "s"} kept in Pending.` : "Cancelled — nothing was added.");
      return;
    }
    setRunSummary({ startedAt, note, results });
    const failed = results.filter((r) => !r.ok);
    if (failed.length) setGenError(failed[failed.length - 1].error ?? "Couldn't generate a post right now — try again.");
  }

  function downloadRunReport() {
    if (!runSummary) return;
    const ok = runSummary.results.filter((r) => r.ok);
    const failed = runSummary.results.filter((r) => !r.ok);
    const lines = [
      "CAMPAIGNFORGE — RUN REPORT",
      `Client: ${clientLabel(active)}`,
      "Triggered by: Generate post",
      `Run at: ${new Date(runSummary.startedAt).toLocaleString()}`,
      ...(runSummary.note ? [`About: ${runSummary.note}`] : []),
      `Drafts created: ${ok.length}${failed.length ? ` (${failed.length} failed)` : ""}`,
      "",
      ...ok.map(
        (r, i) => `${i + 1}. ${platformLabel(r.platform)}\n   ${r.preview}${(r.preview?.length ?? 0) >= 140 ? "…" : ""}`
      ),
      ...(failed.length ? ["", "Failed:", ...failed.map((r) => `- ${platformLabel(r.platform)}: ${r.error ?? ""}`)] : []),
      "",
      "Every draft above landed in Pending — nothing here was scheduled or published automatically. Review and approve each one in Posts › Queue.",
    ];
    downloadTextFile(`campaignforge-run-${runSummary.startedAt.slice(0, 10)}.txt`, lines.join("\n"));
    trackFeature("run-report-download");
  }

  // --- Bulk actions ---

  const selectable = tab !== "published";
  const selectedPosts = visible.filter((p) => selectedIds.has(p.id));
  const allSelected = visible.length > 0 && selectedPosts.length === visible.length;

  async function bulkApprove() {
    setBulkBusy("approve");
    let approved = 0;
    const flagged: QueuePost[] = [];
    let failed = 0;
    // One moderation pass per post — a bulk click never skips the check.
    for (const post of selectedPosts) {
      try {
        await postsApi.approve(post.id, false);
        approved++;
      } catch (err) {
        if (apiErrorCode(err) === "moderation_flagged") flagged.push(post);
        else failed++;
      }
    }
    setBulkBusy(null);
    setSelectedIds(new Set());
    const parts = [`${approved} approved`];
    if (flagged.length) parts.push(`${flagged.length} flagged by moderation — still Pending, review each one`);
    if (failed) parts.push(`${failed} failed`);
    (flagged.length || failed ? toast.warning : toast.success)(parts.join(" · "));
    if (approved) trackFeature("post-bulk-approve", { count: approved });
    reload();
    void refreshClients();
  }

  async function bulkPublish() {
    setBulkBusy("publish");
    const eligible = selectedPosts.filter((p) => canPublish(p.platform));
    let ok = 0;
    let failed = 0;
    for (const post of eligible) {
      try {
        await api.publishContent(post.id);
        ok++;
      } catch {
        failed++;
      }
    }
    setBulkBusy(null);
    setBulkPublishOpen(false);
    setSelectedIds(new Set());
    const skipped = selectedPosts.length - eligible.length;
    const parts = [`${ok} published`];
    if (failed) parts.push(`${failed} failed — see the Failed tab`);
    if (skipped) parts.push(`${skipped} skipped (platform can't be published to yet)`);
    (failed || skipped ? toast.warning : toast.success)(parts.join(" · "));
    if (ok) trackFeature("post-bulk-publish", { count: ok });
    reload();
    void refreshClients();
  }

  // --- Render ---------------------------------------------------------------

  const pageCount = Math.max(1, Math.ceil(total / PER_PAGE));
  const empty = EMPTY[tab];
  const tabLabel = QUEUE_TABS.find((t) => t.status === tab)?.label ?? tab;
  const filtered = platform !== "all" || Boolean(search.trim());

  const statSource = scope === "all" ? clients : active ? [active] : [];
  const sum = (k: "published" | "total_posts" | "pending" | "approved" | "scheduled") =>
    statSource.length ? statSource.reduce((n, c) => n + (c[k] ?? 0), 0) : null;
  const inQueue = statSource.length ? (sum("pending") ?? 0) + (sum("approved") ?? 0) + (sum("scheduled") ?? 0) : null;

  const noClient = !clientsLoading && !activeId;
  const canGenerate = Boolean(active?.has_brand_profile) && !atLimit;

  const generateControl = active && (
    <div className="flex flex-wrap items-center gap-2">
      {!active.has_brand_profile ? (
        <Link href="/setup/profile" className={buttonVariants({ size: "sm", variant: "secondary" })}>
          <Wand2 className="h-3.5 w-3.5" /> Set up the brand profile to generate
        </Link>
      ) : (
        <>
          <Button size="sm" disabled={Boolean(generating) || !canGenerate} onClick={() => setGenModalOpen(true)}>
            {generating ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Writing for {platformLabel(generating)}…
              </>
            ) : (
              <>
                <Wand2 className="h-3.5 w-3.5" /> Generate post
              </>
            )}
          </Button>
          {generating && (
            <button
              type="button"
              onClick={() => genAbort.current?.abort()}
              className="font-mono text-[11px] text-muted underline hover:text-ink"
            >
              Cancel
            </button>
          )}
          <QuotaHint used={used} limit={limit} />
        </>
      )}
    </div>
  );

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Posts"
        title="Queue"
        description="Every post waits here for a person. Approving runs a moderation check first; only approved posts can be scheduled or published."
        actions={
          <>
            <SegmentedTabs
              label="Queue scope"
              items={[
                { id: "client" as Scope, label: clientLabel(active) },
                { id: "all" as Scope, label: "All clients" },
              ]}
              value={scope}
              onChange={(s) => {
                setScope(s);
                setPage(1);
              }}
            />
            <Link href="/calendar" className={buttonVariants({ variant: "secondary", size: "sm" })}>
              <CalendarDays className="h-3.5 w-3.5" />
              Calendar
            </Link>
          </>
        }
      />

      {noClient ? (
        <EmptyState
          icon={Inbox}
          title="Add a client first"
          description="Posts belong to a client. Add one, set up its brand profile, then generate its first post here."
          action={
            <Link href="/clients?new=1" className={buttonVariants({ size: "sm" })}>
              Add a client
            </Link>
          }
        />
      ) : (
        <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)]">
          {/* Sidebar — Cadence's profile / channels / usage column, for the active client */}
          <aside className="space-y-5">
            {active && (
              <ClientProfileCard
                name={clientLabel(active)}
                website={active.website_url}
                audience={profile?.target_audience ?? null}
                voice={profile?.voice_description ?? null}
                hasProfile={active.has_brand_profile}
              />
            )}
            {active && (
              <Panel className="p-5 motion-safe:animate-screen-in" style={{ animationDelay: "0.08s" }}>
                <div className="flex items-center justify-between">
                  <Eyebrow>Channels</Eyebrow>
                  <Link href="/setup/accounts" className="font-mono text-[10.5px] text-accent-text underline">
                    Manage
                  </Link>
                </div>
                <div className="mt-3 space-y-2">
                  {channels === null ? (
                    <div className="flex h-16 items-center justify-center">
                      <Loader2 className="h-4 w-4 animate-spin text-muted" />
                    </div>
                  ) : (
                    channels.supported.map((id) => (
                      <AccountChip key={id} platform={id} connected={connected.includes(id)} />
                    ))
                  )}
                </div>
                {channels && connected.length === 0 && (
                  <p className="mt-3 text-[11px] leading-snug text-muted">
                    You can draft posts right now. Connect accounts in Setup when you&apos;re ready to publish.
                  </p>
                )}
              </Panel>
            )}
            <div className="space-y-2">
              <UsageMeter used={used} limit={limit} plan={sub?.plan_tier ?? null} delay={0.06} />
              <MiniStat icon={<TrendingUp className="h-3.5 w-3.5" />} label="POSTS PUBLISHED" value={sum("published")} delay={0.1} />
              <MiniStat icon={<FileText className="h-3.5 w-3.5" />} label="TOTAL POSTS" value={sum("total_posts")} delay={0.16} />
              <MiniStat icon={<ListChecks className="h-3.5 w-3.5" />} label="IN QUEUE" value={inQueue} delay={0.22} />
            </div>
            <Link href="/analytics" className="block font-mono text-[11px] text-accent-text">
              View full insights →
            </Link>
          </aside>

          {/* Queue */}
          <div className="min-w-0">
            <CampaignIndicator />
            <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
              <QueueTabs active={tab} counts={counts} onChange={changeTab} />
              {generateControl}
            </div>

            <div className="mt-1 flex flex-wrap items-center gap-2">
              <PlatformFilterRow
                platforms={filterPlatforms}
                value={platform}
                onChange={(v) => {
                  setPlatform(v);
                  setPage(1);
                }}
              />
              <SearchInput value={search} onChange={setSearch} placeholder="Search posts…" />
            </div>
            {search && items.length < total && (
              <p className="mt-1 font-mono text-[11px] text-muted">
                Search covers the {items.length} posts on this page of {total}.
              </p>
            )}

            {selectable && visible.length > 0 && (
              <div className="mt-2 flex flex-wrap items-center gap-3 font-mono text-[11px]">
                <button
                  type="button"
                  onClick={() => setSelectedIds(allSelected ? new Set() : new Set(visible.map((p) => p.id)))}
                  className="flex items-center gap-1.5 text-muted hover:text-ink"
                >
                  <span
                    className={cn(
                      "flex h-3.5 w-3.5 items-center justify-center rounded-sm border",
                      allSelected ? "border-accent bg-accent text-on-accent" : "border-slate-300"
                    )}
                  >
                    {allSelected && <Check className="h-2.5 w-2.5" />}
                  </span>
                  {selectedIds.size > 0 ? `${selectedPosts.length} selected` : "Select all"}
                </button>
                {selectedPosts.length > 0 && (
                  <>
                    {tab === "draft" && (
                      <button
                        type="button"
                        onClick={() => void bulkApprove()}
                        disabled={bulkBusy !== null}
                        className="flex items-center gap-1 text-emerald-600 underline disabled:opacity-50"
                      >
                        {bulkBusy === "approve" && <Loader2 className="h-3 w-3 animate-spin" />}
                        Approve {selectedPosts.length}
                      </button>
                    )}
                    {(tab === "approved" || tab === "scheduled") && (
                      <button
                        type="button"
                        onClick={() => setBulkPublishOpen(true)}
                        disabled={bulkBusy !== null}
                        className="text-emerald-600 underline disabled:opacity-50"
                      >
                        Publish {selectedPosts.length}
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => deletePosts(selectedPosts)}
                      disabled={bulkBusy !== null}
                      className="text-red-600 underline disabled:opacity-50"
                    >
                      Delete {selectedPosts.length}
                    </button>
                    <button type="button" onClick={() => setSelectedIds(new Set())} className="text-muted">
                      Cancel
                    </button>
                  </>
                )}
              </div>
            )}

            {atLimit && active?.has_brand_profile ? (
              <ErrorBanner
                message={`You've used all ${limit} generations this period. Upgrade under Settings › Billing to keep going.`}
              />
            ) : genError ? (
              <ErrorBanner message={genError} onRetry={() => setGenModalOpen(true)} />
            ) : null}
            {runSummary && runSummary.results.some((r) => r.ok) && (
              <div
                role="status"
                aria-live="polite"
                className="mt-3 flex items-center justify-between gap-3 rounded-lg border border-emerald-300 bg-emerald-50/70 px-3 py-2 motion-safe:animate-screen-in"
              >
                <div className="font-mono text-[11px] text-emerald-700">
                  <CheckCircle2 className="mr-1.5 inline h-3 w-3 align-[-1px]" />
                  {(() => {
                    const ok = runSummary.results.filter((r) => r.ok);
                    const by = ok.reduce<Record<string, number>>((acc, r) => ({ ...acc, [r.platform]: (acc[r.platform] ?? 0) + 1 }), {});
                    return `Added ${ok.length} draft${ok.length === 1 ? "" : "s"} to Pending — ${Object.entries(by)
                      .map(([id, n]) => `${platformLabel(id)} ×${n}`)
                      .join(", ")}`;
                  })()}
                </div>
                <div className="flex shrink-0 items-center gap-3">
                  <button type="button" onClick={downloadRunReport} className="font-mono text-[10.5px] text-emerald-700 underline underline-offset-2">
                    Download report
                  </button>
                  <button type="button" onClick={() => setRunSummary(null)} aria-label="Dismiss" className="text-muted">
                    <X className="h-3 w-3" />
                  </button>
                </div>
              </div>
            )}

            <div className="mt-4">
              {loading && items.length === 0 ? (
                <div className="flex h-48 items-center justify-center" aria-live="polite">
                  <Loader2 className="h-6 w-6 animate-spin text-accent" />
                  <span className="sr-only">Loading posts</span>
                </div>
              ) : loadError ? (
                <Panel className="flex flex-col items-center gap-3 px-6 py-12 text-center">
                  <p className="text-sm font-medium text-ink">Could not load the queue</p>
                  <p className="max-w-md text-sm text-muted">{loadError}</p>
                  <Button variant="secondary" size="sm" onClick={reload}>
                    <RefreshCw className="h-3.5 w-3.5" />
                    Try again
                  </Button>
                </Panel>
              ) : visible.length === 0 ? (
                <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-slate-300 px-6 py-14 text-center text-muted motion-safe:animate-screen-in">
                  <ListChecks className="h-5 w-5" />
                  {filtered ? (
                    <>
                      <span className="font-mono text-xs">
                        {search.trim()
                          ? `No posts matching "${search.trim()}".`
                          : `No ${platformLabel(platform)} posts in ${tabLabel}.`}
                      </span>
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => {
                          setSearch("");
                          setPlatform("all");
                          setPage(1);
                        }}
                      >
                        Clear filters
                      </Button>
                    </>
                  ) : (
                    <>
                      <span className="font-mono text-xs text-ink">{empty.title}</span>
                      <span className="max-w-md text-[12.5px]">{empty.body}</span>
                      {tab === "draft" && (
                        <Link href="/amplify" className={cn(buttonVariants({ variant: "secondary", size: "sm" }), "mt-1")}>
                          <Layers className="h-3.5 w-3.5" /> Amplify a post
                        </Link>
                      )}
                    </>
                  )}
                </div>
              ) : (
                <div className={cn("space-y-3 transition-opacity", loading && "opacity-60")} aria-busy={loading}>
                  {visible.map((post) => (
                    <PostCard
                      key={post.id}
                      post={post}
                      clientName={scope === "all" ? clientNames.get(post.client_id) ?? null : null}
                      busy={busy[post.id] ?? null}
                      editing={editingId === post.id}
                      now={now}
                      removing={removing.has(post.id)}
                      selected={selectedIds.has(post.id)}
                      onToggleSelect={selectable ? onToggleSelect : undefined}
                      onApprove={onApprove}
                      onEditStart={onEditStart}
                      onEditClose={onEditClose}
                      onEditSave={onEditSave}
                      onSchedule={onSchedule}
                      onPublish={onPublish}
                      onDelete={onDelete}
                      onRegenerate={onRegenerate}
                      onCancelRegenerate={onCancelRegenerate}
                      onRequestBrief={onRequestBrief}
                      onCancelBrief={onCancelBrief}
                    />
                  ))}
                </div>
              )}
            </div>

            {pageCount > 1 && (
              <div className="mt-4 flex items-center justify-center gap-3">
                <Button variant="secondary" size="sm" disabled={page <= 1 || loading} onClick={() => setPage((p) => p - 1)}>
                  <ChevronLeft className="h-3.5 w-3.5" /> Previous
                </Button>
                <span className="font-mono text-xs text-muted">
                  {page} / {pageCount}
                </span>
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={page >= pageCount || loading}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Next <ChevronRight className="h-3.5 w-3.5" />
                </Button>
              </div>
            )}
          </div>
        </div>
      )}

      <ModerationWarning
        open={moderation !== null}
        postTitle={moderation?.post.title ?? ""}
        issues={moderation?.issues ?? []}
        busy={moderation ? busy[moderation.post.id] === "approve" : false}
        onClose={() => setModeration(null)}
        onEdit={() => {
          if (moderation) setEditingId(moderation.post.id);
          setModeration(null);
        }}
        onOverride={() => moderation && void approve(moderation.post, true)}
      />

      <ScheduleDialog
        open={scheduleFor !== null}
        mode={scheduleFor?.status === "scheduled" ? "reschedule" : "schedule"}
        platform={scheduleFor?.platform ?? ""}
        clientName={scheduleFor ? clientNames.get(scheduleFor.client_id) ?? null : null}
        currentAt={scheduleFor?.scheduled_at}
        busy={scheduleFor ? busy[scheduleFor.id] === "schedule" : false}
        onClose={() => setScheduleFor(null)}
        onConfirm={(iso) => scheduleFor && void schedule(scheduleFor, iso)}
      />

      <PublishConfirm
        open={publishFor !== null}
        platform={publishFor?.platform ?? ""}
        clientName={publishFor ? clientNames.get(publishFor.client_id) ?? null : null}
        busy={publishFor ? busy[publishFor.id] === "publish" : false}
        onClose={() => setPublishFor(null)}
        onConfirm={() => publishFor && void publish(publishFor)}
      />

      <PostDialog
        open={bulkPublishOpen}
        onOpenChange={(o) => !o && setBulkPublishOpen(false)}
        busy={bulkBusy === "publish"}
        title={`Publish ${selectedPosts.length} post${selectedPosts.length === 1 ? "" : "s"} now?`}
        description="Each one posts immediately to its client's live, connected account. Published posts cannot be unpublished from here."
        footer={
          <>
            <Button variant="secondary" onClick={() => setBulkPublishOpen(false)} disabled={bulkBusy === "publish"}>
              Cancel
            </Button>
            <Button onClick={() => void bulkPublish()} disabled={bulkBusy === "publish"}>
              {bulkBusy === "publish" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              Publish now
            </Button>
          </>
        }
      >
        {selectedPosts.some((p) => !canPublish(p.platform)) && (
          <p className="text-xs text-amber-800">
            {selectedPosts.filter((p) => !canPublish(p.platform)).length} selected post(s) will be skipped:{" "}
            {publishUnavailableReason(selectedPosts.find((p) => !canPublish(p.platform))?.platform)}
          </p>
        )}
      </PostDialog>

      <GeneratePostsModal
        open={genModalOpen}
        platforms={pickable}
        remaining={remaining}
        footnote={
          connected.length === 0
            ? "No accounts connected yet — drafting works without one; publishing needs a connected account."
            : undefined
        }
        onCancel={() => setGenModalOpen(false)}
        onConfirm={(p, note) => void runGeneration(p, note)}
      />
    </div>
  );
}
