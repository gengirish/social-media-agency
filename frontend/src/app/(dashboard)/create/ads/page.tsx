"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Info, Loader2, Megaphone, UserPlus, Wand2 } from "lucide-react";
import { toast } from "sonner";
import { api, apiErrorStatus, isGenerationQuotaError, type SubscriptionInfo } from "@/lib/api";
import { adSetText, adsApi, type AdNetwork, type AdSet } from "@/lib/api-ads";
import { clientLabel, useActiveClient } from "@/lib/active-client";
import { trackFeature } from "@/lib/analytics";
import { Button, buttonVariants } from "@/components/ui/button";
import { CampaignIndicator } from "@/components/ui/campaign-indicator";
import { EmptyState, LoadingState } from "@/components/ui/empty-state";
import { ErrorBanner, undoToast } from "@/components/ui/feedback";
import { Eyebrow } from "@/components/ui/panel";
import { QuotaHint } from "@/components/ui/quota-hint";
import { SearchInput } from "@/components/ui/search-input";
import { SegmentedTabs } from "@/components/ui/tabs";
import { AdSetCard } from "@/components/ads/ad-set-card";
import { cn } from "@/lib/utils";

const MODES: { id: AdNetwork; label: string }[] = [
  { id: "google", label: "Google Ads" },
  { id: "meta", label: "Meta Ads" },
];

const COPY: Record<AdNetwork, { eyebrow: string; tagline: string; button: string; blurb: string }> = {
  google: {
    eyebrow: "Google Ads agent",
    tagline: "Catch intent that already exists",
    button: "Generate RSA set",
    blurb:
      "Google is intent-driven: people are already searching for this. Writes a full 15-headline, 4-description Responsive Search Ad plus sitelinks, callouts, keyword themes and negative keywords, every asset checked against Google's real character limits. Competitor names are deliberately kept out of the copy — you can bid on a rival's name as a keyword, but putting it in ad text risks disapproval.",
  },
  meta: {
    eyebrow: "Meta Ads agent",
    tagline: "Earn the scroll-stop",
    button: "Generate Meta ads",
    blurb:
      "Meta is interruption-driven: nobody is looking for you. Writes primary text, headlines and descriptions to Meta's visible thresholds, not its much larger hard caps — copy past ~125 characters is silently truncated for real viewers while looking fine in Ads Manager. Also pre-checks the personal-attributes policy, Meta's most-violated rule.",
  },
};

export default function AdsPage() {
  const router = useRouter();
  const { active, activeId, loading: clientsLoading, error: clientsError, refresh } = useActiveClient();

  const [mode, setMode] = useState<AdNetwork>("google");
  const [items, setItems] = useState<AdSet[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState(false);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const [subscription, setSubscription] = useState<SubscriptionInfo | null>(null);
  const [quotaBlocked, setQuotaBlocked] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const loadSubscription = useCallback(() => {
    api
      .getSubscription()
      .then(setSubscription)
      .catch(() => setSubscription(null)); // unknown quota renders nothing, never a guess
  }, []);

  const loadList = useCallback(async (clientId: string) => {
    setListLoading(true);
    setListError(false);
    try {
      const { items } = await adsApi.list(clientId);
      setItems(items);
    } catch {
      setListError(true);
    } finally {
      setListLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSubscription();
    return () => controllerRef.current?.abort();
  }, [loadSubscription]);

  useEffect(() => {
    setItems([]);
    setGenError(null);
    if (activeId) void loadList(activeId);
  }, [activeId, loadList]);

  const used = subscription?.generations_used ?? null;
  const limit = subscription?.generations_limit ?? null;
  const atLimit = quotaBlocked || (used != null && limit != null && used >= limit);
  const noProfile = !!active && !active.has_brand_profile;

  async function generate() {
    if (!activeId || atLimit || noProfile || generating) return;
    setGenError(null);
    const controller = new AbortController();
    controllerRef.current = controller;
    setGenerating(true);
    const network = mode;
    try {
      const created = await adsApi.generate(activeId, network, controller.signal);
      setItems((prev) => [created, ...prev.filter((i) => i.id !== created.id)]);
      trackFeature("ads", { network });
    } catch (err) {
      if (controller.signal.aborted) {
        // The request is abandoned client-side; the server may still have
        // finished it, so re-read rather than pretend nothing happened.
        toast("Cancelled — if the set was already written, it will still appear below.");
        void loadList(activeId);
      } else if (isGenerationQuotaError(err)) {
        setQuotaBlocked(true);
      } else if (apiErrorStatus(err) === 404) {
        setGenError("That client no longer exists in this workspace.");
        void refresh();
      } else {
        setGenError("Couldn't generate ad copy right now — no quota was used. Try again.");
      }
    } finally {
      controllerRef.current = null;
      setGenerating(false);
      loadSubscription();
    }
  }

  function cancel() {
    controllerRef.current?.abort();
  }

  function copy(item: AdSet) {
    const text = adSetText(item.payload);
    navigator.clipboard
      .writeText(text)
      .then(() => {
        setCopiedId(item.id);
        window.setTimeout(() => setCopiedId((c) => (c === item.id ? null : c)), 1800);
      })
      .catch(() => toast.error("Couldn't copy — your browser blocked clipboard access."));
  }

  function remove(item: AdSet) {
    setHidden((prev) => new Set(prev).add(item.id));
    const unhide = () =>
      setHidden((prev) => {
        const next = new Set(prev);
        next.delete(item.id);
        return next;
      });
    undoToast("Ad set deleted", unhide, () => {
      adsApi
        .remove(item.id)
        .then(() => {
          setItems((prev) => prev.filter((i) => i.id !== item.id));
          unhide();
        })
        .catch(() => {
          unhide();
          toast.error("Couldn't delete that ad set — it's been restored.");
        });
    });
  }

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return items.filter(
      (i) =>
        i.payload?.network === mode &&
        !hidden.has(i.id) &&
        (!q || i.title.toLowerCase().includes(q) || adSetText(i.payload).toLowerCase().includes(q))
    );
  }, [items, mode, hidden, query]);
  const totalForMode = items.filter((i) => i.payload?.network === mode && !hidden.has(i.id)).length;

  if (clientsLoading) return <LoadingState label="Loading clients" />;
  if (clientsError && !active) {
    return <ErrorBanner message="Couldn't load your clients." onRetry={() => void refresh()} />;
  }
  if (!active) {
    return (
      <div>
        <h1 className="mb-6 font-display text-2xl font-semibold text-ink">Ads</h1>
        <EmptyState
          icon={Megaphone}
          title="Add a client first"
          description="Ad copy is written in a client's brand voice, so it needs a client to write for."
          action={
            <Link href="/clients?new=1" className={buttonVariants()}>
              <UserPlus className="h-3.5 w-3.5" /> Add a client
            </Link>
          }
        />
      </div>
    );
  }

  const c = COPY[mode];
  const platformName = mode === "google" ? "Google Ads" : "Meta";
  const canGenerate = !generating && !atLimit && !noProfile;

  return (
    <div>
      <CampaignIndicator />
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <Eyebrow>
          {c.eyebrow} · {clientLabel(active)}
        </Eyebrow>
        <SegmentedTabs items={MODES} value={mode} onChange={setMode} label="Ad network" />
      </div>

      <h1 className="font-display text-2xl font-semibold tracking-tight text-ink">Ads</h1>
      <div className="mb-5 mt-1 flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-display text-[21px] text-ink">{c.tagline}</h2>
        <div className="flex items-center gap-2">
          <Button onClick={generate} disabled={!canGenerate} className={cn(canGenerate && "animate-breathe")}>
            {generating ? (
              <>
                <Loader2 className="h-[13px] w-[13px] animate-spin" /> Writing…
              </>
            ) : (
              <>
                <Wand2 className="h-[13px] w-[13px]" /> {c.button}
              </>
            )}
          </Button>
          {generating && (
            <button type="button" onClick={cancel} className="font-mono text-[11px] text-muted underline">
              Cancel
            </button>
          )}
          <QuotaHint used={used} limit={limit} />
        </div>
      </div>

      <p className="mb-4 max-w-[620px] text-xs leading-relaxed text-muted">{c.blurb}</p>

      <div className="mb-5 flex max-w-[620px] items-start gap-2 rounded-lg border border-sky-300 bg-sky-50 px-3 py-2.5">
        <Info aria-hidden className="mt-0.5 h-[13px] w-[13px] shrink-0 text-sky-600" />
        <p className="text-[11.5px] leading-normal text-slate-600">
          <b className="text-ink">Copy and structure only.</b> No {platformName} account is connected — CampaignForge
          writes the copy and structure, it can&apos;t create campaigns, set budgets, launch anything, or spend money.
          You paste this into {mode === "google" ? "Google Ads" : "Ads Manager"} yourself.
          {mode === "meta" && " It also can't make the image or video, which on Meta matters more than the copy does."}{" "}
          Nothing here predicts CTR, CPC, ROAS or conversions — there is no ad account data, and guessing at numbers
          you&apos;d spend real money against would be worse than saying nothing.
        </p>
      </div>

      {noProfile ? (
        <ErrorBanner
          message={`Set up ${clientLabel(active)}'s brand profile before generating ad copy.`}
          onRetry={() => router.push("/setup/profile")}
          retryLabel="Go to Setup"
        />
      ) : atLimit ? (
        <ErrorBanner
          message={`You've used all ${limit != null ? `${limit} ` : ""}generations this period. Upgrade in Billing to keep going.`}
          onRetry={() => router.push("/pricing")}
          retryLabel="Open Billing"
        />
      ) : (
        genError && <ErrorBanner message={genError} onRetry={generate} />
      )}

      {totalForMode > 0 && (
        <div className="mt-4 flex items-center justify-between gap-3">
          <span className="font-mono text-[11px] text-muted">
            {query ? `${visible.length} of ${totalForMode}` : totalForMode} {mode === "google" ? "Google" : "Meta"} ad{" "}
            {totalForMode === 1 && !query ? "set" : "sets"}
          </span>
          <SearchInput value={query} onChange={setQuery} placeholder="Search ad sets…" />
        </div>
      )}

      <div className="mt-4 space-y-3">
        {listLoading && items.length === 0 ? (
          <LoadingState label="Loading ad sets" className="h-40" />
        ) : listError ? (
          <ErrorBanner message="Couldn't load saved ad sets." onRetry={() => activeId && void loadList(activeId)} />
        ) : totalForMode === 0 && !generating ? (
          <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-slate-300 py-16 text-muted">
            <Megaphone className="h-5 w-5" aria-hidden />
            <span className="font-mono text-xs">
              No {mode === "google" ? "Google" : "Meta"} ad sets yet — generate your first
            </span>
          </div>
        ) : visible.length === 0 && query ? (
          <p className="py-10 text-center font-mono text-xs text-muted">No ad sets match &ldquo;{query}&rdquo;</p>
        ) : (
          visible.map((it, i) => (
            <AdSetCard
              key={it.id}
              item={it}
              delay={Math.min(i, 8) * 0.06}
              onDelete={remove}
              onCopy={copy}
              copied={copiedId === it.id}
            />
          ))
        )}
      </div>
    </div>
  );
}
