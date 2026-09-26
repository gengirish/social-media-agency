"use client";

import { useState } from "react";
import Link from "next/link";
import { format } from "date-fns";
import { ChevronDown, Loader2 } from "lucide-react";
import {
  amplifyApi,
  type AmplifyPack,
  type AmplifyPackDetail,
  type AmplifyPlatformStatus,
} from "@/lib/api";
import { Panel } from "@/components/ui/panel";
import { StatusBadge } from "@/components/ui/status-badge";
import { cn } from "@/lib/utils";
import { angleLabel, platformLabel } from "./labels";

function sourceLabel(pack: AmplifyPack): string {
  if (pack.source_content_id) return pack.source_title?.trim() || "Content piece (untitled)";
  if (pack.source_asset_id) return pack.source_title?.trim() || "Saved content (untitled)";
  if (pack.source_excerpt) return `“${pack.source_excerpt}${pack.source_excerpt.length >= 140 ? "…" : ""}”`;
  // A content-sourced pack stores no text, so once its source piece is deleted
  // (FK is ON DELETE SET NULL) there is nothing left to show.
  return "Source deleted";
}

/**
 * What to say about a platform that produced no draft.
 *
 * Atoms are never stored — `commit` writes the kept ones to `content_piece` and
 * the rest are gone — so when a pack both dropped atoms and came back short,
 * which happened to a given platform is genuinely unknowable. Saying so beats
 * picking one (CF-15).
 */
function statusText(status: AmplifyPlatformStatus, ambiguous: boolean): string {
  if (status === "queued") return "Queued";
  if (status === "not_generated") return "Nothing generated";
  return ambiguous ? "Not kept, or not generated" : "Generated, not kept";
}

const STATUS_TONE: Record<AmplifyPlatformStatus, string> = {
  queued: "text-emerald-700",
  not_kept: "text-muted",
  not_generated: "text-amber-700",
};

function PackDetail({ detail }: { detail: AmplifyPackDetail }) {
  // Both a shortfall at generation and a drop at review can leave a platform
  // with nothing, and the pack records neither per platform.
  const ambiguous = detail.dropped_count > 0 && detail.atom_count < detail.platforms.length;

  return (
    <div className="space-y-4 border-t border-line bg-canvas/40 px-4 py-3">
      <div>
        <p className="font-mono text-[10px] uppercase tracking-wide text-muted">Per platform</p>
        <ul className="mt-1.5 space-y-1">
          {detail.platform_breakdown.map(({ platform, status }) => (
            <li key={platform} className="flex items-center justify-between text-[12.5px]">
              <span className="text-ink">{platformLabel(platform)}</span>
              <span className={STATUS_TONE[status]}>{statusText(status, ambiguous)}</span>
            </li>
          ))}
        </ul>
      </div>

      {detail.posts.length > 0 && (
        <div>
          <p className="font-mono text-[10px] uppercase tracking-wide text-muted">
            Drafts this pack queued
          </p>
          <ul className="mt-1.5 space-y-1.5">
            {detail.posts.map((post) => (
              <li key={post.id} className="rounded-md bg-panel/70 px-2.5 py-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[12.5px] font-medium text-ink">
                    {platformLabel(post.platform)}
                  </span>
                  {post.angle && (
                    <span className="font-mono text-[10px] text-muted">{angleLabel(post.angle)}</span>
                  )}
                  <StatusBadge status={post.status} className="ml-auto" />
                </div>
                {post.excerpt && (
                  <p className="mt-1 line-clamp-2 text-[12px] leading-relaxed text-muted">
                    {post.excerpt}
                  </p>
                )}
              </li>
            ))}
          </ul>
          <Link href="/content" className="mt-2 inline-block font-mono text-[11px] text-accent-text underline">
            Open the queue
          </Link>
        </div>
      )}

      {detail.posts.length === 0 && (
        <p className="text-[12.5px] text-muted">
          Nothing from this pack was kept, so there are no drafts to show. Generated atoms
          aren&apos;t stored — only the ones you keep become drafts.
        </p>
      )}
    </div>
  );
}

/** Recent packs for the workspace. Counts are straight from the pack rows. */
export function PackHistory({ packs, loading }: { packs: AmplifyPack[]; loading: boolean }) {
  // CF-15: a history row could not be opened, so "2 generated · 2 queued" across
  // five platforms was the whole story. Opening one fetches its breakdown.
  const [openId, setOpenId] = useState<string | null>(null);
  const [details, setDetails] = useState<Record<string, AmplifyPackDetail>>({});
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [failedId, setFailedId] = useState<string | null>(null);

  async function toggle(packId: string) {
    if (openId === packId) {
      setOpenId(null);
      return;
    }
    setOpenId(packId);
    setFailedId(null);
    if (details[packId]) return; // already fetched, and packs are immutable
    setLoadingId(packId);
    try {
      const detail = await amplifyApi.pack(packId);
      setDetails((prev) => ({ ...prev, [packId]: detail }));
    } catch {
      setFailedId(packId);
    } finally {
      setLoadingId(null);
    }
  }

  return (
    <section aria-labelledby="amplify-history" className="space-y-3">
      <h2 id="amplify-history" className="text-lg font-semibold text-ink">
        Recent packs
      </h2>
      <Panel className="overflow-hidden">
        {loading ? (
          <p className="p-4 text-sm text-muted">Loading…</p>
        ) : packs.length === 0 ? (
          <p className="p-4 text-sm text-muted">No packs yet. Generated packs show up here, whether or not you kept them.</p>
        ) : (
          <ul className="divide-y divide-line">
            {packs.map((pack) => {
              const open = openId === pack.id;
              return (
                <li key={pack.id}>
                  <button
                    type="button"
                    onClick={() => void toggle(pack.id)}
                    aria-expanded={open}
                    className="flex w-full flex-col gap-1 px-4 py-3 text-left transition-colors hover:bg-slate-500/5 sm:flex-row sm:items-center sm:gap-4"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-ink">{sourceLabel(pack)}</p>
                      <p className="truncate text-xs text-muted">
                        {pack.client_name ?? "Client"} · {pack.platforms.map(platformLabel).join(", ")}
                      </p>
                    </div>
                    <p className="shrink-0 font-mono text-xs text-muted">
                      {pack.atom_count} generated ·{" "}
                      <span className={pack.committed_count > 0 ? "text-ink" : undefined}>
                        {pack.committed_count > 0 ? `${pack.committed_count} queued` : "not queued"}
                      </span>
                    </p>
                    {pack.created_at && (
                      <time dateTime={pack.created_at} className="shrink-0 font-mono text-xs text-muted">
                        {format(new Date(pack.created_at), "d MMM, HH:mm")}
                      </time>
                    )}
                    <ChevronDown
                      aria-hidden
                      className={cn(
                        "h-3.5 w-3.5 shrink-0 text-muted transition-transform",
                        open && "rotate-180"
                      )}
                    />
                  </button>

                  {open && loadingId === pack.id && (
                    <p className="flex items-center gap-2 border-t border-line bg-canvas/40 px-4 py-3 text-xs text-muted">
                      <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading this pack…
                    </p>
                  )}
                  {open && failedId === pack.id && (
                    <p className="border-t border-line bg-canvas/40 px-4 py-3 text-xs text-muted">
                      Couldn&apos;t load this pack. Try opening it again.
                    </p>
                  )}
                  {open && details[pack.id] && <PackDetail detail={details[pack.id]} />}
                </li>
              );
            })}
          </ul>
        )}
      </Panel>
    </section>
  );
}
