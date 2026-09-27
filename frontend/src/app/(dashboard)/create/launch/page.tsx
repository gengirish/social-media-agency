"use client";

import { useCallback, useMemo, useState } from "react";
import { Rocket } from "lucide-react";
import { trackFeature } from "@/lib/analytics";
import type { CreativeAsset } from "@/lib/api-foundation";
import {
  createKitsApi,
  type CommunityKitPayload,
  type LaunchKitPayload,
  type LaunchMode,
  type OutreachPitchPayload,
} from "@/lib/api-create-kits";
import { useActiveClient } from "@/lib/active-client";
import { CampaignIndicator } from "@/components/ui/campaign-indicator";
import { PageHeader } from "@/components/ui/panel";
import { SearchInput } from "@/components/ui/search-input";
import { ErrorBanner } from "@/components/ui/feedback";
import { LoadingState } from "@/components/ui/empty-state";
import {
  CancelLink,
  ClientGate,
  GenerateBanner,
  GenerateButton,
  ListEmpty,
  QuotaFor,
  matchesSearch,
  useCopied,
  useGenerationQuota,
  useGenerator,
  useKitAssets,
} from "@/components/create-kits/kit-shared";
import {
  CommunityKitCard,
  LaunchKitCard,
  OutreachPitchCard,
  communityKitCopyText,
  launchKitCopyText,
  outreachCopyText,
} from "@/components/create-kits/launch-cards";
import { PrfaqPanel } from "@/components/create-kits/prfaq-panel";
import { cn } from "@/lib/utils";

/** Cadence's MODE_META, with "product" copy adapted to "client". */
const MODE_META: Record<
  LaunchMode,
  { label: string; title: string; desc: string; empty: string; generatingLabel: string; cta: string; search: string }
> = {
  launch_kit: {
    label: "Product launch",
    title: "One shot — make it count",
    desc: "Most products only get one real launch day — generate a few different angles here and pick the strongest. No Product Hunt or press-list integration — you submit and send these yourself.",
    empty: "No launch kits yet — generate your first angle",
    generatingLabel: "Drafting…",
    cta: "Generate launch kit",
    search: "Search launch kits…",
  },
  community_kit: {
    label: "Community kit",
    title: "A space people actually return to",
    desc: "No Discord/Slack bot deployment — this generates a setup kit (channels, welcome message, engagement prompts) you configure yourself.",
    empty: "No community kits yet — generate your first one",
    generatingLabel: "Designing…",
    cta: "Generate community kit",
    search: "Search community kits…",
  },
  outreach_pitch: {
    label: "Partnership outreach",
    title: "Cold outreach that isn't cold",
    desc: "No contact database here — this writes the pitch; you supply who to send it to. Nothing is sent from CampaignForge.",
    empty: "No pitches yet — generate your first one",
    generatingLabel: "Pitching…",
    cta: "Generate pitch",
    search: "Search pitches…",
  },
};
const MODES = Object.keys(MODE_META) as LaunchMode[];

/**
 * Create › Launch — Cadence's Launch/PR, Community-Space and
 * Outreach/Partnership agents behind one mode toggle. Every output is a draft
 * the human uses by hand; nothing is submitted, deployed or sent.
 */
export default function LaunchPage() {
  return (
    <div className="space-y-6">
      <CampaignIndicator />
      <PageHeader
        eyebrow="Launch & outreach agents"
        title="Launch"
        description="One-off, external-facing kits: a launch, a community space, a partnership pitch. Drafts only — you submit, set up and send them yourself."
      />
      <ClientGate>
        <LaunchWorkspace />
      </ClientGate>
    </div>
  );
}

function LaunchWorkspace() {
  const { active, activeId } = useActiveClient();
  const [mode, setMode] = useState<LaunchMode>("launch_kit");
  const [search, setSearch] = useState("");
  const quota = useGenerationQuota();
  const gen = useGenerator(activeId);
  const { copiedId, copy } = useCopied();

  const launchKits = useKitAssets<LaunchKitPayload>(activeId, "launch_kit");
  const communityKits = useKitAssets<CommunityKitPayload>(activeId, "community_kit");
  const outreach = useKitAssets<OutreachPitchPayload>(activeId, "outreach_pitch");
  const lists = { launch_kit: launchKits, community_kit: communityKits, outreach_pitch: outreach };
  const list = lists[mode];
  const meta = MODE_META[mode];
  const noProfile = !active?.has_brand_profile;

  const generate = useCallback(async () => {
    if (!activeId || noProfile || quota.exhausted) return;
    const target = mode;
    const result = await gen.run((signal) => createKitsApi.generateLaunch<never>(activeId, target, signal));
    if (result) {
      if (target === "launch_kit") launchKits.prepend(result);
      else if (target === "community_kit") communityKits.prepend(result);
      else outreach.prepend(result);
      trackFeature(`create-launch-${target.replace("_", "-")}`);
    }
    quota.reload();
  }, [activeId, noProfile, quota, gen, mode, launchKits, communityKits, outreach]);

  const copyLaunch = useCallback(
    (item: CreativeAsset<LaunchKitPayload>) => void copy(item.id, launchKitCopyText(item.payload)),
    [copy]
  );
  const copyCommunity = useCallback(
    (item: CreativeAsset<CommunityKitPayload>) => void copy(item.id, communityKitCopyText(item.payload)),
    [copy]
  );
  const copyOutreach = useCallback(
    (item: CreativeAsset<OutreachPitchPayload>) => void copy(item.id, outreachCopyText(item.payload)),
    [copy]
  );
  const deleteLaunch = useCallback(
    (item: CreativeAsset<LaunchKitPayload>) => launchKits.removeWithUndo(item, "Draft deleted."),
    [launchKits]
  );
  const deleteCommunity = useCallback(
    (item: CreativeAsset<CommunityKitPayload>) => communityKits.removeWithUndo(item, "Draft deleted."),
    [communityKits]
  );
  const deleteOutreach = useCallback(
    (item: CreativeAsset<OutreachPitchPayload>) => outreach.removeWithUndo(item, "Draft deleted."),
    [outreach]
  );

  const visibleCount = useMemo(
    () => (list.items as CreativeAsset<unknown>[]).filter((i) => matchesSearch(i, search)).length,
    [list.items, search]
  );
  const filter = <P,>(items: CreativeAsset<P>[]) => items.filter((i) => matchesSearch(i as CreativeAsset<unknown>, search));

  return (
    <div>
      <div className="mb-5 flex flex-wrap items-center gap-1.5" role="group" aria-label="Launch mode">
        {MODES.map((id, i) => {
          const on = mode === id;
          return (
            <button
              key={id}
              type="button"
              aria-pressed={on}
              onClick={() => {
                setMode(id);
                setSearch("");
                gen.clear();
              }}
              style={{ animationDelay: `${i * 0.04}s` }}
              className={cn(
                "press-scale rounded-md border px-3 py-1.5 text-xs font-medium transition-all duration-200 motion-safe:animate-chip-in",
                on ? "border-accent/35 bg-accent/10 text-accent-text" : "border-line text-muted hover:text-ink"
              )}
            >
              {MODE_META[id].label}
            </button>
          );
        })}
      </div>

      {mode === "launch_kit" && activeId && (
        <PrfaqPanel clientId={activeId} disabled={noProfile || quota.exhausted} onCharged={quota.reload} />
      )}

      <div key={mode} className="motion-safe:animate-screen-in">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-display text-[21px] text-ink">{meta.title}</h2>
          <div className="flex items-center gap-3">
            <GenerateButton
              onClick={() => void generate()}
              generating={gen.generating}
              disabled={noProfile || quota.exhausted}
              label={meta.cta}
              generatingLabel={meta.generatingLabel}
            />
            {gen.generating && <CancelLink onClick={gen.cancel} />}
            <QuotaFor quota={quota} />
          </div>
        </div>
        <p className="mb-5 max-w-[620px] text-xs leading-relaxed text-muted">{meta.desc}</p>
      </div>

      <GenerateBanner
        noProfile={noProfile}
        quotaExhausted={quota.exhausted}
        failure={gen.failure}
        message={gen.message}
        onRetry={() => void generate()}
        fallback="Couldn't generate right now — no quota was used. Try again."
        profileMessage="Set up this client's brand profile before generating this."
      />

      {list.items.length > 0 && (
        <div className="mt-5 flex items-center justify-between gap-3">
          <span className="font-mono text-[11px] text-muted">
            {search ? `${visibleCount} of ${list.items.length}` : list.items.length}{" "}
            {list.items.length === 1 ? "draft" : "drafts"}
          </span>
          <SearchInput value={search} onChange={setSearch} placeholder={meta.search} />
        </div>
      )}

      <div className="mt-4 space-y-3">
        {list.loading ? (
          <LoadingState label="Loading drafts…" className="h-40" />
        ) : list.loadError ? (
          <ErrorBanner message="Couldn't load these drafts." onRetry={() => void list.reload()} />
        ) : list.items.length === 0 && !gen.generating ? (
          <ListEmpty icon={Rocket} text={meta.empty} />
        ) : visibleCount === 0 && search ? (
          <ListEmpty icon={Rocket} text={`Nothing matches “${search}”`} />
        ) : mode === "launch_kit" ? (
          filter(launchKits.items).map((item, i) => (
            <LaunchKitCard
              key={item.id}
              item={item}
              index={i}
              copied={copiedId === item.id}
              onCopy={copyLaunch}
              onDelete={deleteLaunch}
            />
          ))
        ) : mode === "community_kit" ? (
          filter(communityKits.items).map((item, i) => (
            <CommunityKitCard
              key={item.id}
              item={item}
              index={i}
              copied={copiedId === item.id}
              onCopy={copyCommunity}
              onDelete={deleteCommunity}
            />
          ))
        ) : (
          filter(outreach.items).map((item, i) => (
            <OutreachPitchCard
              key={item.id}
              item={item}
              index={i}
              copied={copiedId === item.id}
              onCopy={copyOutreach}
              onDelete={deleteOutreach}
            />
          ))
        )}
      </div>
    </div>
  );
}
