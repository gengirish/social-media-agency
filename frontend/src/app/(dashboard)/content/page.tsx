"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { format } from "date-fns";
import { toast } from "sonner";
import { CalendarDays, ChevronLeft, ChevronRight, Inbox, Layers, Loader2, RefreshCw, Search } from "lucide-react";
import {
  api,
  apiErrorCode,
  moderationIssues,
  postsApi,
  type Client,
  type ModerationIssue,
  type QueuePost,
  type QueueStatus,
} from "@/lib/api";
import { trackFeature } from "@/lib/analytics";
import { Button, buttonVariants } from "@/components/ui/button";
import { PageHeader, Panel } from "@/components/ui/panel";
import { cn } from "@/lib/utils";
import { ModerationWarning } from "@/components/posts/moderation-warning";
import { PostCard, type PostAction, type PostEdit } from "@/components/posts/post-card";
import { PublishConfirm } from "@/components/posts/publish-confirm";
import { QUEUE_PLATFORMS } from "@/components/posts/platform";
import { QUEUE_TABS, QueueTabs } from "@/components/posts/queue-tabs";
import { ScheduleDialog } from "@/components/posts/schedule-dialog";

const PER_PAGE = 50;

const EMPTY: Record<QueueStatus, { title: string; body: string }> = {
  draft: {
    title: "Nothing waiting for review",
    body: "Posts from campaigns and Amplify land here as Pending. Each one needs a person to approve it — after a moderation check — before it can be scheduled or published.",
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

const selectClass =
  "h-9 rounded-md border border-line bg-panel/70 px-2.5 text-sm text-ink outline-none transition-colors focus:border-accent";

type Counts = Partial<Record<QueueStatus, number | null>>;

export default function QueuePage() {
  const [tab, setTab] = useState<QueueStatus>("draft");
  const [clientId, setClientId] = useState("");
  const [platform, setPlatform] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);

  const [items, setItems] = useState<QueuePost[]>([]);
  const [total, setTotal] = useState(0);
  const [counts, setCounts] = useState<Counts>({});
  const [clients, setClients] = useState<Client[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [busy, setBusy] = useState<Record<string, PostAction>>({});
  const [editingId, setEditingId] = useState<string | null>(null);
  const [moderation, setModeration] = useState<{ post: QueuePost; issues: ModerationIssue[] } | null>(null);
  const [scheduleFor, setScheduleFor] = useState<QueuePost | null>(null);
  const [publishFor, setPublishFor] = useState<QueuePost | null>(null);
  const [now, setNow] = useState(() => Date.now());

  // Overdue badges depend on the clock, not just on data.
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 60_000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    api
      .getClientsForLookup()
      .then(setClients)
      .catch(() => setClients([]));
  }, []);

  const clientNames = useMemo(() => new Map(clients.map((c) => [c.id, c.brand_name])), [clients]);

  // A newer request supersedes an older one; stale responses are dropped.
  const loadSeq = useRef(0);
  const load = useCallback(async () => {
    const seq = ++loadSeq.current;
    const filters = { client_id: clientId || undefined, platform: platform || undefined };
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
    try {
      const res = await postsApi.list({ ...filters, content_status: tab, page, per_page: PER_PAGE });
      if (seq !== loadSeq.current) return;
      setItems(res.items);
      setTotal(res.total);
    } catch (err) {
      if (seq !== loadSeq.current) return;
      setItems([]);
      setTotal(0);
      setLoadError(err instanceof Error ? err.message : "Could not load posts");
    } finally {
      if (seq === loadSeq.current) setLoading(false);
    }
    const c = await countsP;
    if (seq === loadSeq.current) setCounts(Object.fromEntries(c));
  }, [tab, clientId, platform, page]);

  useEffect(() => {
    load();
  }, [load]);

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return items;
    return items.filter((p) =>
      [p.title, p.body, ...(p.hashtags ?? []), clientNames.get(p.client_id) ?? ""].some((s) =>
        (s ?? "").toLowerCase().includes(q)
      )
    );
  }, [items, search, clientNames]);

  function setPostBusy(id: string, action: PostAction | null) {
    setBusy((prev) => {
      const next = { ...prev };
      if (action) next[id] = action;
      else delete next[id];
      return next;
    });
  }

  function changeTab(status: QueueStatus) {
    setTab(status);
    setPage(1);
    setEditingId(null);
  }

  // --- Actions -----------------------------------------------------------

  async function approve(post: QueuePost, override = false) {
    setPostBusy(post.id, "approve");
    try {
      const res = await postsApi.approve(post.id, override);
      setModeration(null);
      const mod = res.moderation?.status;
      if (mod === "unavailable") {
        toast.warning("Moderation check unavailable — approved without it");
      } else if (override || mod === "overridden") {
        toast.success("Approved — moderation override recorded");
      } else {
        toast.success("Approved — ready to schedule");
      }
      trackFeature("post-approve", { platform: post.platform, override });
      await load();
    } catch (err) {
      const code = apiErrorCode(err);
      if (code === "moderation_flagged") {
        setModeration({ post, issues: moderationIssues(err) });
      } else if (code === "invalid_status") {
        setModeration(null);
        toast.error("This post is no longer Pending — refreshed the queue");
        await load();
      } else {
        toast.error(err instanceof Error ? err.message : "Approve failed");
      }
    } finally {
      setPostBusy(post.id, null);
    }
  }

  async function saveEdit(post: QueuePost, edit: PostEdit) {
    setPostBusy(post.id, "save");
    try {
      const updated = await postsApi.edit(post.id, edit);
      setItems((prev) => prev.map((p) => (p.id === post.id ? { ...p, ...updated } : p)));
      setEditingId(null);
      toast.success("Changes saved");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not save changes");
    } finally {
      setPostBusy(post.id, null);
    }
  }

  function gateError(err: unknown, fallback: string) {
    if (apiErrorCode(err) === "not_approved") {
      toast.error("Approve this post first");
      void load();
    } else if (apiErrorCode(err) === "client_archived") {
      toast.error("This client is archived. Restore it from Setup › Clients to post for it.");
    } else {
      toast.error(err instanceof Error ? err.message : fallback);
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
      await load();
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
      // Report what the API actually returned rather than assuming it worked.
      if (res?.url) {
        const url = res.url;
        toast.success("Published", { action: { label: "View", onClick: () => window.open(url, "_blank", "noopener") } });
      } else {
        toast.success("Publish request accepted");
      }
      await load();
    } catch (err) {
      setPublishFor(null);
      gateError(err, "Publish failed");
      await load();
    } finally {
      setPostBusy(post.id, null);
    }
  }

  // --- Render ------------------------------------------------------------

  const filtered = Boolean(clientId || platform);
  const pageCount = Math.max(1, Math.ceil(total / PER_PAGE));
  const empty = EMPTY[tab];
  const tabLabel = QUEUE_TABS.find((t) => t.status === tab)?.label ?? tab;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Posts"
        title="Queue"
        description="Every post waits here for a person. Approving runs a moderation check first; only approved posts can be scheduled or published."
        actions={
          <>
            <Link href="/calendar" className={buttonVariants({ variant: "secondary", size: "sm" })}>
              <CalendarDays className="h-3.5 w-3.5" />
              Calendar
            </Link>
            <Link href="/amplify" className={buttonVariants({ variant: "secondary", size: "sm" })}>
              <Layers className="h-3.5 w-3.5" />
              Amplify
            </Link>
          </>
        }
      />

      <div className="space-y-3">
        <QueueTabs active={tab} counts={counts} onChange={changeTab} />

        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <label className="relative flex-1">
            <span className="sr-only">Search posts</span>
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search title, text, hashtags, client"
              className={cn(selectClass, "w-full pl-8 placeholder:text-slate-400")}
            />
          </label>
          <div className="grid grid-cols-2 gap-2 sm:flex">
            <select
              aria-label="Filter by client"
              value={clientId}
              onChange={(e) => {
                setClientId(e.target.value);
                setPage(1);
              }}
              className={selectClass}
            >
              <option value="">All clients</option>
              {clients.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.brand_name}
                </option>
              ))}
            </select>
            <select
              aria-label="Filter by platform"
              value={platform}
              onChange={(e) => {
                setPlatform(e.target.value);
                setPage(1);
              }}
              className={selectClass}
            >
              <option value="">All platforms</option>
              {QUEUE_PLATFORMS.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </select>
          </div>
        </div>
        {search && items.length < total && (
          <p className="font-mono text-[11px] text-muted">
            Search covers the {items.length} posts on this page of {total}.
          </p>
        )}
      </div>

      {loading && items.length === 0 ? (
        <div className="flex h-48 items-center justify-center" aria-live="polite">
          <Loader2 className="h-6 w-6 animate-spin text-accent" />
          <span className="sr-only">Loading posts</span>
        </div>
      ) : loadError ? (
        <Panel className="flex flex-col items-center gap-3 px-6 py-12 text-center">
          <p className="text-sm font-medium text-ink">Could not load the queue</p>
          <p className="max-w-md text-sm text-muted">{loadError}</p>
          <Button variant="secondary" size="sm" onClick={() => load()}>
            <RefreshCw className="h-3.5 w-3.5" />
            Try again
          </Button>
        </Panel>
      ) : visible.length === 0 ? (
        <Panel dashed className="flex flex-col items-center px-6 py-14 text-center">
          <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-full border border-line bg-canvas">
            <Inbox className="h-5 w-5 text-muted" />
          </div>
          {search || filtered ? (
            <>
              <h2 className="text-base font-semibold text-ink">No {tabLabel.toLowerCase()} posts match</h2>
              <p className="mt-1 max-w-md text-sm text-muted">
                {search ? "Nothing on this page matches your search." : "Nothing in this tab for the selected filters."}
              </p>
              <Button
                variant="secondary"
                size="sm"
                className="mt-4"
                onClick={() => {
                  setSearch("");
                  setClientId("");
                  setPlatform("");
                  setPage(1);
                }}
              >
                Clear filters
              </Button>
            </>
          ) : (
            <>
              <h2 className="text-base font-semibold text-ink">{empty.title}</h2>
              <p className="mt-1 max-w-md text-sm text-muted">{empty.body}</p>
              {tab === "draft" && (
                <div className="mt-4 flex flex-wrap justify-center gap-2">
                  <Link href="/campaigns" className={buttonVariants({ size: "sm" })}>
                    Start a campaign
                  </Link>
                  <Link href="/amplify" className={buttonVariants({ variant: "secondary", size: "sm" })}>
                    Amplify a post
                  </Link>
                </div>
              )}
            </>
          )}
        </Panel>
      ) : (
        <div className={cn("space-y-3 transition-opacity", loading && "opacity-60")} aria-busy={loading}>
          {visible.map((post) => (
            <PostCard
              key={post.id}
              post={post}
              clientName={clientNames.get(post.client_id) ?? null}
              busy={busy[post.id] ?? null}
              editing={editingId === post.id}
              now={now}
              onApprove={() => approve(post)}
              onEditStart={() => setEditingId(post.id)}
              onEditCancel={() => setEditingId(null)}
              onEditSave={(edit) => saveEdit(post, edit)}
              onSchedule={() => setScheduleFor(post)}
              onPublish={() => setPublishFor(post)}
            />
          ))}
        </div>
      )}

      {pageCount > 1 && (
        <div className="flex items-center justify-center gap-3">
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
        onOverride={() => moderation && approve(moderation.post, true)}
      />

      <ScheduleDialog
        open={scheduleFor !== null}
        mode={scheduleFor?.status === "scheduled" ? "reschedule" : "schedule"}
        platform={scheduleFor?.platform ?? ""}
        clientName={scheduleFor ? clientNames.get(scheduleFor.client_id) ?? null : null}
        currentAt={scheduleFor?.scheduled_at}
        busy={scheduleFor ? busy[scheduleFor.id] === "schedule" : false}
        onClose={() => setScheduleFor(null)}
        onConfirm={(iso) => scheduleFor && schedule(scheduleFor, iso)}
      />

      <PublishConfirm
        open={publishFor !== null}
        platform={publishFor?.platform ?? ""}
        clientName={publishFor ? clientNames.get(publishFor.client_id) ?? null : null}
        busy={publishFor ? busy[publishFor.id] === "publish" : false}
        onClose={() => setPublishFor(null)}
        onConfirm={() => publishFor && publish(publishFor)}
      />
    </div>
  );
}
