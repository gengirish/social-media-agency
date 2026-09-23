"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { Inbox as InboxIcon, Loader2, RefreshCw, UserPlus } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { inboxApi, type InboxItem, type InboxResponse, type ReplySuggestion } from "@/lib/api-inbox";
import { clientLabel, useActiveClient } from "@/lib/active-client";
import { Eyebrow } from "@/components/ui/panel";
import { buttonVariants } from "@/components/ui/button";
import { ErrorBanner } from "@/components/ui/feedback";
import { PlatformFilterRow } from "@/components/ui/platform-filter";
import { AccountBanners } from "@/components/inbox/account-banners";
import { InboxDetail } from "@/components/inbox/inbox-detail";
import { InboxListItem } from "@/components/inbox/inbox-list-item";
import { cn } from "@/lib/utils";

type TypeFilter = "all" | "unread" | "mention" | "comment" | "dm";

const FILTERS: [TypeFilter, string][] = [
  ["all", "All"],
  ["unread", "Unread"],
  ["mention", "Mentions"],
  ["comment", "Comments"],
  ["dm", "DMs"],
];

const INBOX_PLATFORMS = ["twitter", "linkedin"];

function Dashed({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-[10px] border border-dashed border-slate-300 px-4 py-14 text-center text-muted motion-safe:animate-screen-in">
      <InboxIcon className="h-5 w-5" />
      {children}
    </div>
  );
}

export default function InboxPage() {
  const { active, activeId, loading: clientsLoading, error: clientsError, refresh: refreshClients } = useActiveClient();

  const [data, setData] = useState<InboxResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filter, setFilter] = useState<TypeFilter>("all");
  const [platformFilter, setPlatformFilter] = useState("all");
  const [suggestions, setSuggestions] = useState<Record<string, ReplySuggestion>>({});
  const [generations, setGenerations] = useState<{ used?: number; limit?: number }>({});
  const requestRef = useRef(0);

  const loadGenerations = useCallback(() => {
    api
      .getSubscription()
      .then((s) => setGenerations({ used: s.generations_used, limit: s.generations_limit }))
      .catch(() => setGenerations({})); // unknown quota renders nothing, never a guess
  }, []);

  const load = useCallback(
    async (refresh = false) => {
      if (!activeId) return;
      const ticket = ++requestRef.current;
      if (refresh) setRefreshing(true);
      else setLoading(true);
      setLoadError(false);
      try {
        const res = await inboxApi.get(activeId, refresh);
        if (ticket !== requestRef.current) return; // client switched mid-flight
        setData(res);
      } catch {
        if (ticket === requestRef.current) setLoadError(true);
      } finally {
        if (ticket === requestRef.current) {
          setLoading(false);
          setRefreshing(false);
        }
      }
    },
    [activeId]
  );

  useEffect(() => {
    setData(null);
    setSelectedId(null);
    setSuggestions({});
    setPlatformFilter("all");
    void load();
  }, [load]);

  useEffect(() => loadGenerations(), [loadGenerations]);

  const accounts = useMemo(() => data?.accounts ?? [], [data]);
  const items = useMemo(() => data?.items ?? [], [data]);
  // Channel filter offers only platforms with a connected account behind them.
  const connectedPlatforms = useMemo(
    () =>
      INBOX_PLATFORMS.filter((p) => accounts.some((a) => a.platform === p && a.account_id && a.status !== "unsupported")),
    [accounts]
  );
  const noAccountsConnected = data !== null && connectedPlatforms.length === 0;
  const anyReadable = accounts.some((a) => a.status === "ok");

  const filtered = items.filter((m) => {
    if (platformFilter !== "all" && m.platform !== platformFilter) return false;
    if (filter === "all") return true;
    if (filter === "unread") return !m.read && !m.handled;
    return m.type === filter;
  });
  const selected = items.find((m) => m.id === selectedId) ?? null;
  const unreadCount = items.filter((m) => !m.read && !m.handled).length;

  const patchItem = (id: string, patch: Partial<InboxItem>) =>
    setData((prev) => (prev ? { ...prev, items: prev.items.map((m) => (m.id === id ? { ...m, ...patch } : m)) } : prev));

  const select = (item: InboxItem) => {
    setSelectedId(item.id);
    if (!item.read && activeId) {
      patchItem(item.id, { read: true });
      // Read state is a convenience; a failed save just leaves the dot on next load.
      inboxApi.setState({ client_id: activeId, item_id: item.id, read: true }).catch(() => undefined);
    }
  };

  const toggleHandled = async () => {
    if (!selected || !activeId) return;
    const next = !selected.handled;
    patchItem(selected.id, { handled: next });
    try {
      await inboxApi.setState({ client_id: activeId, item_id: selected.id, handled: next });
    } catch {
      patchItem(selected.id, { handled: !next });
      toast.error("Couldn't save that — try again.");
    }
  };

  if (clientsLoading) {
    return (
      <div className="flex items-center justify-center gap-2 py-24 font-mono text-xs text-muted">
        <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading your workspace…
      </div>
    );
  }

  if (clientsError) {
    return (
      <div className="mx-auto max-w-2xl py-14">
        <h1 className="font-display text-xl text-ink">Inbox</h1>
        <ErrorBanner message="We couldn't load your clients." onRetry={() => void refreshClients()} />
      </div>
    );
  }

  if (!active || !activeId) {
    return (
      <div className="mx-auto max-w-2xl animate-screen-in py-14">
        <Eyebrow>Inbox</Eyebrow>
        <h1 className="mt-3 font-display text-xl text-ink">Inbox</h1>
        <p className="mt-2 max-w-[480px] text-[13.5px] text-slate-600">
          Mentions and comments are read per client, from that client&apos;s connected accounts. Add a client first.
        </p>
        <Link href="/clients?new=1" className={cn(buttonVariants(), "mt-6 w-fit")}>
          <UserPlus className="h-3.5 w-3.5" /> Add a client
        </Link>
      </div>
    );
  }

  const selectedAccount = selected ? accounts.find((a) => a.account_id === selected.account_id) : undefined;

  return (
    <div className="mx-auto max-w-7xl py-2">
      <div className="mb-2 flex flex-wrap items-center gap-3">
        <h1 className="font-display text-xl font-semibold text-ink">Inbox</h1>
        {unreadCount > 0 && (
          <span className="rounded-full border border-accent/35 bg-accent/10 px-2.5 py-1 text-[11px] font-medium text-accent-text motion-safe:animate-pop-in">
            {unreadCount} unread
          </span>
        )}
        <button
          type="button"
          onClick={() => void load(true)}
          disabled={loading || refreshing}
          className="press-scale ml-auto flex items-center gap-1.5 font-mono text-[11px] text-muted hover:text-ink disabled:opacity-60"
        >
          <RefreshCw className={cn("h-3 w-3", refreshing && "animate-spin")} /> Refresh
        </button>
      </div>
      <p className="mb-5 max-w-[560px] text-[11.5px] leading-relaxed text-muted">
        Live mentions and comments from {clientLabel(active)}&apos;s connected accounts, fetched from the platforms each
        time you open this page. Replies post to the real account only when you click Send and confirm, and moderation
        checks every reply first.
      </p>

      {loadError && <ErrorBanner message="Couldn't load the inbox." onRetry={() => void load()} />}

      {data && <AccountBanners accounts={accounts} onRetry={() => void load(true)} />}

      <div className="grid gap-4 min-[861px]:grid-cols-[360px_minmax(0,1fr)]">
        {/* left: message list */}
        <div>
          <div className="mb-3 flex flex-wrap gap-1.5 font-mono text-[11px]" role="group" aria-label="Filter by type">
            {FILTERS.map(([key, label]) => (
              <button
                key={key}
                type="button"
                aria-pressed={filter === key}
                onClick={() => setFilter(key)}
                title={key === "dm" && data ? data.dms.reason : undefined}
                className={cn(
                  "press-scale rounded-md border px-2.5 py-1 transition-all duration-200",
                  filter === key ? "border-accent/35 bg-accent/10 text-accent-text" : "border-line text-muted hover:text-ink"
                )}
              >
                {label}
                {key === "dm" && data && !data.dms.available && <span className="ml-1 text-[9.5px] opacity-70">n/a</span>}
              </button>
            ))}
          </div>
          {connectedPlatforms.length > 1 && (
            <div className="mb-3">
              <PlatformFilterRow platforms={connectedPlatforms} value={platformFilter} onChange={setPlatformFilter} size="small" />
            </div>
          )}

          <div className="space-y-2">
            {loading && !data && (
              <div role="status" className="flex items-center justify-center gap-2 py-14 font-mono text-xs text-muted">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Reading connected accounts…
              </div>
            )}

            {filtered.map((m, i) => (
              <InboxListItem
                key={m.id}
                item={m}
                active={m.id === selectedId}
                onClick={() => select(m)}
                delay={Math.min(i, 12) * 0.04}
              />
            ))}

            {data && filtered.length === 0 && (
              <>
                {noAccountsConnected ? (
                  <Dashed>
                    <span className="max-w-[240px] font-mono text-xs leading-relaxed">
                      Connect an X or LinkedIn account in Setup to start receiving mentions and comments here.
                    </span>
                    <Link href="/setup/accounts" className="font-mono text-[11.5px] text-accent-text underline">
                      Go to Setup
                    </Link>
                  </Dashed>
                ) : filter === "dm" && !data.dms.available ? (
                  <Dashed>
                    <span className="max-w-[260px] font-mono text-xs leading-relaxed">{data.dms.reason}</span>
                  </Dashed>
                ) : !anyReadable ? (
                  <Dashed>
                    <span className="max-w-[240px] font-mono text-xs leading-relaxed">
                      None of this client&apos;s accounts could be read — see the notices above for why.
                    </span>
                  </Dashed>
                ) : items.length === 0 ? (
                  <Dashed>
                    <span className="max-w-[260px] font-mono text-xs leading-relaxed">
                      No mentions or comments in the latest fetch. X returns the 20 most recent mentions; LinkedIn
                      comments are read from posts CampaignForge published.
                    </span>
                  </Dashed>
                ) : (
                  <Dashed>
                    <span className="font-mono text-xs">Nothing here</span>
                  </Dashed>
                )}
              </>
            )}
          </div>
        </div>

        {/* right: thread detail */}
        {selected && (
          <InboxDetail
            key={selected.id}
            item={selected}
            account={selectedAccount}
            clientId={activeId}
            suggestion={suggestions[selected.id]}
            onSuggestion={(s) => setSuggestions((prev) => ({ ...prev, [selected.id]: s }))}
            onToggleHandled={toggleHandled}
            onSent={(url) => patchItem(selected.id, { handled: true, read: true, reply_url: url })}
            generationsUsed={generations.used}
            generationsLimit={generations.limit}
            onGenerated={loadGenerations}
            hasBrandProfile={active.has_brand_profile}
          />
        )}
      </div>
    </div>
  );
}
