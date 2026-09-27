"use client";

import { useCallback, useMemo, useState } from "react";
import { Mail } from "lucide-react";
import { trackFeature } from "@/lib/analytics";
import type { CreativeAsset } from "@/lib/api-foundation";
import {
  EMAIL_CAMPAIGN_TYPES,
  createKitsApi,
  type EmailCampaignPayload,
  type EmailCampaignType,
} from "@/lib/api-create-kits";
import { clientLabel, useActiveClient } from "@/lib/active-client";
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
import { EmailCampaignCard, emailCopyText, senderName } from "@/components/create-kits/email-card";
import { cn } from "@/lib/utils";

/**
 * Create › Email — Cadence's Email/Lifecycle agent. Five lifecycle campaign
 * types; each generate writes one campaign for the active client. Drafts only:
 * CampaignForge has no email-sending integration for a client's customers.
 */
export default function EmailPage() {
  return (
    <div className="space-y-6">
      <CampaignIndicator />
      <PageHeader
        eyebrow="Email / lifecycle agent"
        title="Email"
        description={
          <>
            An owned channel — not at an algorithm&apos;s mercy.{" "}
            <span className="text-muted">
              CampaignForge drafts these emails; it doesn&apos;t send them. Copy each campaign into whatever you already send
              from (Mailchimp, Resend, etc.).
            </span>
          </>
        }
      />
      <ClientGate>
        <EmailWorkspace />
      </ClientGate>
    </div>
  );
}

function EmailWorkspace() {
  const { active, activeId } = useActiveClient();
  const [campaignType, setCampaignType] = useState<EmailCampaignType>("welcome");
  const [search, setSearch] = useState("");
  const quota = useGenerationQuota();
  const gen = useGenerator(activeId);
  const list = useKitAssets<EmailCampaignPayload>(activeId, "email_campaign");
  const { copiedId, copy } = useCopied();

  const noProfile = !active?.has_brand_profile;
  const sender = senderName(active?.website_url, active ? clientLabel(active) : "");

  const generate = useCallback(async () => {
    if (!activeId || noProfile || quota.exhausted) return;
    const result = await gen.run((signal) => createKitsApi.generateEmail(activeId, campaignType, signal));
    if (result) {
      list.prepend(result);
      trackFeature("create-email", { campaign_type: campaignType });
    }
    quota.reload();
  }, [activeId, noProfile, quota, gen, campaignType, list]);

  const onCopy = useCallback(
    (item: CreativeAsset<EmailCampaignPayload>) => void copy(item.id, emailCopyText(item.payload)),
    [copy]
  );
  const onDelete = useCallback(
    (item: CreativeAsset<EmailCampaignPayload>) => list.removeWithUndo(item, "Campaign deleted."),
    [list]
  );

  const visible = useMemo(() => list.items.filter((i) => matchesSearch(i, search)), [list.items, search]);

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-1.5" role="group" aria-label="Campaign type">
        {EMAIL_CAMPAIGN_TYPES.map((t, i) => {
          const on = campaignType === t.id;
          return (
            <button
              key={t.id}
              type="button"
              aria-pressed={on}
              onClick={() => setCampaignType(t.id)}
              style={{ animationDelay: `${i * 0.04}s` }}
              className={cn(
                "press-scale rounded-md border px-3 py-1.5 text-xs font-medium transition-all duration-200 motion-safe:animate-chip-in",
                on ? "border-accent/35 bg-accent/10 text-accent-text" : "border-line text-muted hover:text-ink"
              )}
            >
              {t.label}
            </button>
          );
        })}
        <div className="ml-auto flex items-center gap-3">
          <GenerateButton
            onClick={() => void generate()}
            generating={gen.generating}
            disabled={noProfile || quota.exhausted}
            label="Generate campaign"
            generatingLabel="Writing…"
          />
          {gen.generating && <CancelLink onClick={gen.cancel} />}
          <QuotaFor quota={quota} />
        </div>
      </div>

      <GenerateBanner
        noProfile={noProfile}
        quotaExhausted={quota.exhausted}
        failure={gen.failure}
        message={gen.message}
        onRetry={() => void generate()}
        fallback="Couldn't generate a campaign right now — no quota was used. Try again."
        profileMessage="Set up this client's brand profile before generating campaigns."
      />

      {list.items.length > 0 && (
        <div className="mt-5 flex items-center justify-between gap-3">
          <span className="font-mono text-[11px] text-muted">
            {search ? `${visible.length} of ${list.items.length}` : list.items.length}{" "}
            {list.items.length === 1 ? "campaign" : "campaigns"}
          </span>
          <SearchInput value={search} onChange={setSearch} placeholder="Search campaigns…" />
        </div>
      )}

      <div className="mt-4 space-y-3">
        {list.loading ? (
          <LoadingState label="Loading campaigns…" className="h-40" />
        ) : list.loadError ? (
          <ErrorBanner message="Couldn't load this client's campaigns." onRetry={() => void list.reload()} />
        ) : list.items.length === 0 && !gen.generating ? (
          <ListEmpty icon={Mail} text="No campaigns yet — pick a type above and generate one" />
        ) : visible.length === 0 && search ? (
          <ListEmpty icon={Mail} text={`No campaigns match “${search}”`} />
        ) : (
          visible.map((item, i) => (
            <EmailCampaignCard
              key={item.id}
              item={item}
              index={i}
              sender={sender}
              copied={copiedId === item.id}
              onCopy={onCopy}
              onDelete={onDelete}
            />
          ))
        )}
      </div>
    </div>
  );
}
