"use client";

/*
 * Create › Content — Cadence's ContentScreen. Four generators behind one mode
 * toggle (Niche scan first, as in Cadence), each saving a creative asset for
 * the active client. Nothing here enters the post queue: long-form content has
 * no platform and no publish path, so it is copied or exported. Amplify is the
 * way from a saved piece into Pending posts.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { AlertTriangle, ListChecks, Loader2, Scan, Search, UserPlus, Wand2 } from "lucide-react";
import { api, apiErrorStatus, isGenerationQuotaError, ApiError, type SubscriptionInfo } from "@/lib/api";
import { foundationApi } from "@/lib/api-foundation";
import {
  MODE_KIND,
  createContentApi,
  downloadTextFile,
  draftMarkdown,
  exportFilename,
  findSimilarScan,
  parseScanNames,
  type BlogPayload,
  type ComparisonPayload,
  type ContentAsset,
  type ContentMode,
  type NicheScanPayload,
  type VideoScriptPayload,
} from "@/lib/api-create-content";
import { clientLabel, useActiveClient } from "@/lib/active-client";
import { trackFeature } from "@/lib/analytics";
import { cn } from "@/lib/utils";
import { Button, buttonVariants } from "@/components/ui/button";
import { Eyebrow } from "@/components/ui/panel";
import { CampaignIndicator } from "@/components/ui/campaign-indicator";
import { QuotaHint } from "@/components/ui/quota-hint";
import { ErrorBanner, undoToast } from "@/components/ui/feedback";
import { SearchInput } from "@/components/ui/search-input";
import { EmptyState, LoadingState } from "@/components/ui/empty-state";
import { BlogCard, ComparisonCard, NicheScanCard, VideoScriptCard } from "@/components/create-content/cards";

const MODES: { id: ContentMode; label: string }[] = [
  { id: "scan", label: "Niche scan" },
  { id: "seo", label: "Blog post" },
  { id: "compare", label: "Comparison page" },
  { id: "video", label: "Video script" },
];

const AGENT: Record<ContentMode, string> = {
  seo: "SEO content agent",
  compare: "Competitors agent",
  scan: "Niche scan agent",
  video: "Short-form video agent",
};

const HEADLINE: Record<ContentMode, string> = {
  seo: "Content that compounds",
  compare: "Fair fight, real search intent",
  scan: "See the whole board, not one rival",
  video: "Native beats produced",
};

const BLURB: Record<ContentMode, string> = {
  seo: "Unlike social posts, this content doesn't decay in a feed within hours — it's built to rank in search over months. Each draft targets one real keyword with genuine search intent. There's no blog/CMS integration, so copy or export the draft into wherever the client's blog lives.",
  compare:
    "Looks up real, current info on the competitor you name before writing anything (when web search is configured — otherwise the page says it had no live web data). Never invents features or pricing, and always includes one honest place they genuinely win: a comparison that only flatters itself isn't trustworthy.",
  scan: "Name 2-5 real competitors and this scans what's working across all of them — which angles get reused, how saturated each looks, and one gap none of them cover yet. You always name the competitors; nothing here picks them for you or invents a fact about any of them.",
  video:
    "No video generation here — this writes a shootable script (hook, beats, on-screen text, audio style), not the video itself. It doesn't enter the post queue, since there's no video to schedule or publish.",
};

const EMPTY: Record<ContentMode, string> = {
  seo: "No content yet — generate your first blog draft",
  compare: "No comparison pages yet — name a competitor above to generate your first",
  scan: "No scans yet — name 2-5 real competitors above to see the board",
  video: "No scripts yet — generate your first one",
};

const EMPTY_ICON = { seo: Search, compare: ListChecks, scan: Scan, video: Wand2 } as const;

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      ta.remove();
      return ok;
    } catch {
      return false;
    }
  }
}

function errorCode(err: unknown): string | null {
  if (!(err instanceof ApiError)) return null;
  const d = err.detail as { code?: unknown } | null;
  return d && typeof d === "object" && typeof d.code === "string" ? d.code : null;
}

export default function CreateContentPage() {
  const router = useRouter();
  const { active, activeId, clients, loading: clientsLoading } = useActiveClient();

  const [mode, setMode] = useState<ContentMode>("scan");
  const [assets, setAssets] = useState<ContentAsset[]>([]);
  const [listLoading, setListLoading] = useState(false);
  const [listError, setListError] = useState(false);
  const [subscription, setSubscription] = useState<SubscriptionInfo | null>(null);
  const [quotaBlocked, setQuotaBlocked] = useState(false);
  const [profileBlocked, setProfileBlocked] = useState(false);

  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState<string | null>(null);
  const [competitorName, setCompetitorName] = useState("");
  const [scanInput, setScanInput] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [optimizingId, setOptimizingId] = useState<string | null>(null);
  const [aiSeoErrorId, setAiSeoErrorId] = useState<string | null>(null);
  const [gapGeneratingId, setGapGeneratingId] = useState<string | null>(null);
  const [gapErrorId, setGapErrorId] = useState<string | null>(null);

  const genAbort = useRef<AbortController | null>(null);
  const aiSeoAbort = useRef<AbortController | null>(null);
  const gapAbort = useRef<AbortController | null>(null);

  const loadSubscription = useCallback(() => {
    api
      .getSubscription()
      .then(setSubscription)
      .catch(() => setSubscription(null)); // unknown quota renders nothing, never a guess
  }, []);

  const loadAssets = useCallback(async (clientId: string) => {
    setListLoading(true);
    setListError(false);
    try {
      const { items } = await foundationApi.listAssets<ContentAsset["payload"]>({
        clientId,
        kinds: ["niche_scan", "blog_post", "comparison_page", "video_script"],
        limit: 200,
      });
      setAssets(items);
    } catch {
      setListError(true);
    } finally {
      setListLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSubscription();
    return () => {
      genAbort.current?.abort();
      aiSeoAbort.current?.abort();
      gapAbort.current?.abort();
    };
  }, [loadSubscription]);

  useEffect(() => {
    setAssets([]);
    setProfileBlocked(false);
    setGenError(null);
    if (activeId) void loadAssets(activeId);
  }, [activeId, loadAssets]);

  const used = subscription?.generations_used ?? null;
  const limit = subscription?.generations_limit ?? null;
  const atLimit = quotaBlocked || (used != null && limit != null && used >= limit);
  const noProfile = !active?.has_brand_profile || profileBlocked;

  const byKind = useMemo(() => {
    const out: Record<ContentMode, ContentAsset[]> = { scan: [], seo: [], compare: [], video: [] };
    for (const a of assets) {
      const m = (Object.keys(MODE_KIND) as ContentMode[]).find((k) => MODE_KIND[k] === a.kind);
      if (m) out[m].push(a);
    }
    return out;
  }, [assets]);

  const scanNames = parseScanNames(scanInput);
  const similarScan = mode === "scan" ? findSimilarScan(scanNames, byKind.scan) : null;
  const compareDisabled = generating || atLimit || noProfile || !competitorName.trim();
  const scanDisabled = generating || atLimit || noProfile || scanNames.length < 2;
  const plainDisabled = generating || atLimit || noProfile;

  const q = searchQuery.trim().toLowerCase();
  const matches = (a: ContentAsset) => !q || JSON.stringify(a.payload).toLowerCase().includes(q);
  const list = byKind[mode].filter(matches);

  function handleFailure(err: unknown, controller: AbortController, onOther: (msg: string) => void) {
    if (controller.signal.aborted) return; // Cadence: a cancel is not an error
    if (isGenerationQuotaError(err)) {
      setQuotaBlocked(true);
    } else if (errorCode(err) === "brand_profile_required") {
      setProfileBlocked(true);
    } else if (apiErrorStatus(err) === 404) {
      onOther("That client or item no longer exists in this workspace.");
    } else {
      onOther(err instanceof Error && err.message ? err.message : "Couldn't generate content right now — try again.");
    }
  }

  async function generate() {
    if (!activeId || atLimit || noProfile) return;
    if (mode === "compare" && !competitorName.trim()) return;
    if (mode === "scan" && scanNames.length < 2) return;
    const controller = new AbortController();
    genAbort.current = controller;
    setGenerating(true);
    setGenError(null);
    try {
      let created: ContentAsset;
      if (mode === "seo") created = await createContentApi.blog(activeId, controller.signal);
      else if (mode === "compare")
        created = await createContentApi.comparison(activeId, competitorName.trim(), controller.signal);
      else if (mode === "scan") created = await createContentApi.nicheScan(activeId, scanNames, controller.signal);
      else created = await createContentApi.videoScript(activeId, controller.signal);
      setAssets((prev) => [created, ...prev]);
      if (mode === "compare") setCompetitorName("");
      if (mode === "scan") setScanInput("");
      trackFeature("create-content", { mode });
    } catch (err) {
      handleFailure(err, controller, setGenError);
    } finally {
      genAbort.current = null;
      setGenerating(false);
      loadSubscription();
    }
  }

  async function optimizeForAI(asset: ContentAsset) {
    if (atLimit || noProfile) return;
    const controller = new AbortController();
    aiSeoAbort.current = controller;
    setOptimizingId(asset.id);
    setAiSeoErrorId(null);
    try {
      const updated = await createContentApi.optimizeForAi(asset.id, controller.signal);
      setAssets((prev) => prev.map((a) => (a.id === asset.id ? updated : a)));
      trackFeature("ai-seo");
    } catch (err) {
      handleFailure(err, controller, () => setAiSeoErrorId(asset.id));
    } finally {
      aiSeoAbort.current = null;
      setOptimizingId(null);
      loadSubscription();
    }
  }

  async function generateFromGap(scan: ContentAsset) {
    if (atLimit || noProfile) return;
    const controller = new AbortController();
    gapAbort.current = controller;
    setGapGeneratingId(scan.id);
    setGapErrorId(null);
    try {
      const blog = await createContentApi.blogFromGap(scan.id, controller.signal);
      setAssets((prev) => [blog, ...prev]);
      setMode("seo");
      trackFeature("create-content", { mode: "gap-to-blog" });
    } catch (err) {
      handleFailure(err, controller, () => setGapErrorId(scan.id));
    } finally {
      gapAbort.current = null;
      setGapGeneratingId(null);
      loadSubscription();
    }
  }

  // Cadence's undo window: remove now, delete on the server only when the
  // 8-second toast closes without an undo.
  function deletePiece(asset: ContentAsset) {
    const index = assets.findIndex((a) => a.id === asset.id);
    setAssets((prev) => prev.filter((a) => a.id !== asset.id));
    undoToast(
      "Draft deleted.",
      () =>
        setAssets((prev) => {
          if (prev.some((a) => a.id === asset.id)) return prev;
          const next = [...prev];
          next.splice(Math.min(Math.max(index, 0), next.length), 0, asset);
          return next;
        }),
      () => {
        foundationApi.deleteAsset(asset.id).catch(() => {
          toast.error("Couldn't delete that draft — it's back in the list.");
          setAssets((prev) => (prev.some((a) => a.id === asset.id) ? prev : [asset, ...prev]));
        });
      }
    );
  }

  async function copyDraft(asset: ContentAsset) {
    const ok = await copyText(draftMarkdown(asset.kind, asset.payload));
    if (!ok) {
      toast.error("Couldn't copy — your browser blocked clipboard access.");
      return;
    }
    setCopiedId(asset.id);
    setTimeout(() => setCopiedId((id) => (id === asset.id ? null : id)), 1800);
  }

  function exportDraft(asset: ContentAsset) {
    downloadTextFile(exportFilename(asset), draftMarkdown(asset.kind, asset.payload));
  }

  // ---- no client / loading --------------------------------------------------
  if (clientsLoading) return <LoadingState label="Loading your workspace…" />;
  if (clients.length === 0 || !active) {
    return (
      <div className="py-8">
        <h1 className="sr-only">Content</h1>
        <EmptyState
          icon={UserPlus}
          title="Add a client first"
          description="Content is written for a client, in its brand voice. Add the first client you manage to start."
          action={
            <Link href="/clients?new=1" className={buttonVariants()}>
              <UserPlus className="h-3.5 w-3.5" /> Add a client
            </Link>
          }
        />
      </div>
    );
  }

  const generateLabel =
    mode === "seo" ? "Generate blog draft" : mode === "compare" ? "Generate comparison" : mode === "scan" ? "Scan niche" : "Generate video script";
  const busyLabel =
    mode === "seo" ? "Researching & writing…" : mode === "compare" ? "Researching…" : mode === "scan" ? "Scanning…" : "Scripting…";
  const disabled = mode === "compare" ? compareDisabled : mode === "scan" ? scanDisabled : plainDisabled;
  /*
   * Why the button is off, when the reason is something the user can fix here
   * (CF-19). "Scan niche" sat disabled with no explanation until you counted the
   * names yourself. Quota and missing-profile already have their own banners, so
   * they are left to those rather than repeated on the button.
   */
  const disabledReason =
    !disabled || generating || atLimit || noProfile
      ? null
      : mode === "scan" && scanNames.length < 2
        ? "Enter 2–5 competitor names, separated by commas."
        : null;
  const EmptyIcon = EMPTY_ICON[mode];

  return (
    <div className="py-2">
      <CampaignIndicator />
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <Eyebrow>{AGENT[mode]}</Eyebrow>
        <div role="group" aria-label="Content type" className="flex flex-wrap items-center gap-1.5">
          {MODES.map((m) => (
            <button
              key={m.id}
              type="button"
              onClick={() => {
                setMode(m.id);
                setGenError(null);
              }}
              aria-pressed={mode === m.id}
              className={cn(
                "press-scale rounded-md border px-3 py-1.5 text-xs font-medium transition-all duration-200",
                mode === m.id
                  ? "border-accent/40 bg-accent/10 text-accent-text"
                  : "border-line text-muted hover:text-ink"
              )}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>

      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-[21px] font-semibold text-ink">Content</h1>
          <p key={mode} className="font-display text-[15px] text-slate-600 motion-safe:animate-screen-in">
            {HEADLINE[mode]}
          </p>
        </div>
        <form
          className="flex flex-wrap items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (!disabled) void generate();
          }}
        >
          {mode === "compare" && (
            <input
              value={competitorName}
              onChange={(e) => setCompetitorName(e.target.value)}
              placeholder="Competitor name, e.g. Buffer"
              aria-label="Competitor name"
              maxLength={80}
              className="w-[200px] rounded-md border border-line bg-panel px-3 py-1.5 text-[12.5px] text-ink outline-none placeholder:text-muted focus:border-accent"
            />
          )}
          {mode === "scan" && (
            <input
              value={scanInput}
              onChange={(e) => setScanInput(e.target.value)}
              placeholder="2-5 names, comma-separated"
              aria-label="Competitor names, comma-separated"
              className="w-[240px] rounded-md border border-line bg-panel px-3 py-1.5 text-[12.5px] text-ink outline-none placeholder:text-muted focus:border-accent"
            />
          )}
          <Button
            type="submit"
            disabled={disabled}
            title={disabledReason ?? undefined}
            className={cn(!disabled && "animate-breathe")}
          >
            {generating ? (
              <>
                <Loader2 className="h-[13px] w-[13px] animate-spin" /> {busyLabel}
              </>
            ) : (
              <>
                <Wand2 className="h-[13px] w-[13px]" /> {generateLabel}
              </>
            )}
          </Button>
          {disabledReason && (
            <span className="text-[11.5px] text-muted">{disabledReason}</span>
          )}
          {generating && (
            <button
              type="button"
              onClick={() => genAbort.current?.abort()}
              className="font-mono text-[11px] text-muted underline"
            >
              Cancel
            </button>
          )}
          <QuotaHint used={used} limit={limit} />
        </form>
      </div>

      {mode === "scan" && similarScan && (
        <div className="mb-4 flex max-w-[620px] items-center gap-2 rounded-lg border border-sky-300/60 bg-sky-500/5 px-3 py-2 motion-safe:animate-screen-in">
          <AlertTriangle aria-hidden className="h-[13px] w-[13px] shrink-0 text-sky-600" />
          <p className="text-xs leading-normal text-slate-600">
            {similarScan.isExact ? (
              <>
                You scanned <b className="text-ink">this exact set</b> on{" "}
                {new Date((similarScan.scan.payload as NicheScanPayload).scannedAt).toLocaleDateString()} — see it below,
                or scan again for a fresher read.
              </>
            ) : (
              <>
                This overlaps with a scan from{" "}
                {new Date((similarScan.scan.payload as NicheScanPayload).scannedAt).toLocaleDateString()} —{" "}
                <b className="text-ink">{similarScan.shared.length} of these names</b> were included then too.
              </>
            )}
          </p>
        </div>
      )}

      <p className="mb-5 max-w-[620px] text-xs leading-relaxed text-muted">{BLURB[mode]}</p>

      {generating && (
        <p className="-mt-3 mb-4 max-w-[620px] text-[11px] text-muted">
          Cancel stops the wait. If the server has already finished, the result is saved and counts toward your quota.
        </p>
      )}

      {mode === "seo" && byKind.seo.length > 0 && (
        <div className="mb-5 max-w-[620px] rounded-md border border-line bg-slate-500/[0.03] p-3">
          <div className="mb-1.5 text-[11px] font-medium text-muted">
            Keywords already covered — real history, feeds the next draft automatically
          </div>
          <div className="flex flex-wrap gap-1.5">
            {byKind.seo.map((a, i) => (
              <span
                key={a.id}
                className="rounded border border-line px-1.5 py-0.5 font-mono text-[10px] text-slate-600 motion-safe:animate-chip-in"
                style={{ animationDelay: `${Math.min(i, 12) * 0.03}s` }}
              >
                {(a.payload as BlogPayload).keyword}
              </span>
            ))}
          </div>
        </div>
      )}

      {noProfile ? (
        <ErrorBanner
          message={`Set up ${clientLabel(active)}'s brand profile before generating content.`}
          onRetry={() => router.push("/setup/profile")}
          retryLabel="Go to Setup"
        />
      ) : atLimit ? (
        <ErrorBanner
          message={
            limit != null
              ? `You've used all ${limit} generations this billing period. Upgrade to keep going.`
              : "You've used every generation this billing period. Upgrade to keep going."
          }
          onRetry={() => router.push("/pricing")}
          retryLabel="See plans"
        />
      ) : (
        genError && <ErrorBanner message={genError} onRetry={() => void generate()} />
      )}

      <div className="mt-4 space-y-3">
        {assets.length > 0 && (
          <SearchInput value={searchQuery} onChange={setSearchQuery} placeholder="Search this content…" />
        )}
        {listError ? (
          <ErrorBanner message="Couldn't load saved content." onRetry={() => activeId && void loadAssets(activeId)} />
        ) : listLoading && assets.length === 0 ? (
          <LoadingState label="Loading saved content…" className="h-40" />
        ) : (
          list.length === 0 &&
          !generating && (
            <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-slate-300 py-16 text-muted motion-safe:animate-screen-in">
              <EmptyIcon className="h-5 w-5" aria-hidden />
              <span className="px-4 text-center font-mono text-xs">
                {q ? `No results for "${searchQuery.trim()}".` : EMPTY[mode]}
              </span>
            </div>
          )
        )}

        {list.map((asset, i) => {
          const common = {
            delay: Math.min(i, 10) * 0.06,
            copied: copiedId === asset.id,
            onDelete: () => deletePiece(asset),
            onCopy: () => void copyDraft(asset),
            onExport: () => exportDraft(asset),
          };
          if (asset.kind === "blog_post")
            return (
              <BlogCard
                key={asset.id}
                {...common}
                item={asset.payload as BlogPayload}
                optimizing={optimizingId === asset.id}
                aiSeoError={aiSeoErrorId === asset.id}
                onOptimize={() => void optimizeForAI(asset)}
                onCancelOptimize={() => aiSeoAbort.current?.abort()}
              />
            );
          if (asset.kind === "comparison_page")
            return <ComparisonCard key={asset.id} {...common} item={asset.payload as ComparisonPayload} />;
          if (asset.kind === "niche_scan")
            return (
              <NicheScanCard
                key={asset.id}
                {...common}
                item={asset.payload as NicheScanPayload}
                generatingGap={gapGeneratingId === asset.id}
                gapError={gapErrorId === asset.id}
                onGenerateFromGap={() => void generateFromGap(asset)}
                onCancelGap={() => gapAbort.current?.abort()}
              />
            );
          return <VideoScriptCard key={asset.id} {...common} item={asset.payload as VideoScriptPayload} />;
        })}
      </div>
    </div>
  );
}
