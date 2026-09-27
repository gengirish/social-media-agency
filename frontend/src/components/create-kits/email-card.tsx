"use client";

import { memo, useState } from "react";
import { Mail, Sparkles } from "lucide-react";
import type { CreativeAsset } from "@/lib/api-foundation";
import { EMAIL_CAMPAIGN_TYPES, type EmailCampaignPayload, type EmailCampaignType } from "@/lib/api-create-kits";
import { Block, CopyButton, KitCard } from "@/components/create-kits/kit-shared";
import { cn } from "@/lib/utils";

/** Cadence's CAMPAIGN_TYPE_COLORS, mapped onto the themed status hues. */
export const CAMPAIGN_TYPE_TONE: Record<EmailCampaignType, { chip: string; text: string }> = {
  welcome: { chip: "border-emerald-300 bg-emerald-50", text: "text-emerald-700" },
  onboarding: { chip: "border-sky-300 bg-sky-50", text: "text-sky-700" },
  reengagement: { chip: "border-red-300 bg-red-50", text: "text-red-700" },
  update: { chip: "border-accent/30 bg-accent/10", text: "text-accent-text" },
  milestone: { chip: "border-violet-300 bg-violet-50", text: "text-violet-700" },
};

export function campaignTypeLabel(type: string): string {
  return EMAIL_CAMPAIGN_TYPES.find((t) => t.id === type)?.label ?? type;
}

/** Sender name for the preview: the client's website host, else its brand name. */
export function senderName(websiteUrl: string | null | undefined, brandName: string): string {
  const host = (websiteUrl ?? "")
    .trim()
    .replace(/^https?:\/\//i, "")
    .replace(/^www\./i, "")
    .replace(/\/.*$/, "")
    .split(".")[0];
  return host || brandName || "Your brand";
}

export function emailCopyText(p: EmailCampaignPayload): string {
  return `Subject: ${p.subject_line}\nPreview: ${p.preview_text}\n\n${p.body}`;
}

function MetaTile({ label, children, wide }: { label: string; children: string; wide?: boolean }) {
  return (
    <div className={cn("rounded-md border border-line bg-slate-500/5 p-3", wide && "sm:col-span-2")}>
      <div className="mb-1 font-mono text-[9.5px] uppercase tracking-[0.08em] text-muted">{label}</div>
      <div className="text-[12.5px] text-slate-600">{children}</div>
    </div>
  );
}

/** Rendered inbox row + email body, as Cadence's EmailPreview. Nothing is sent. */
function EmailPreview({ p, sender }: { p: EmailCampaignPayload; sender: string }) {
  const tone = CAMPAIGN_TYPE_TONE[p.campaign_type] ?? CAMPAIGN_TYPE_TONE.update;
  return (
    <div className="motion-safe:animate-screen-in">
      <div className="mt-4 overflow-hidden rounded-[10px] border border-line">
        {/* Inbox row */}
        <div className="flex items-center gap-3 border-b border-line bg-slate-500/5 px-4 py-3">
          <div className={cn("flex h-8 w-8 shrink-0 items-center justify-center rounded-full border", tone.chip)}>
            <span className={cn("font-mono text-[11px] font-bold", tone.text)}>{sender[0]?.toUpperCase()}</span>
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[13px] font-semibold text-ink">{sender}</span>
              <span className="font-mono text-[10.5px] text-muted">preview</span>
            </div>
            <div className="mt-px text-[12.5px] font-medium text-ink">{p.subject_line}</div>
            <div className="mt-px truncate text-[11.5px] text-muted">{p.preview_text}</div>
          </div>
        </div>

        {/* Body */}
        <div className="bg-slate-500/[0.03] px-6 py-5">
          <div className="max-w-[520px]">
            <div className="mb-5 flex items-center gap-2 border-b border-line pb-4">
              <div className={cn("flex h-7 w-7 items-center justify-center rounded-md border", tone.chip)}>
                <Sparkles className={cn("h-[13px] w-[13px]", tone.text)} />
              </div>
              <span className="font-mono text-[13px] tracking-[0.05em] text-ink">{sender}</span>
            </div>
            {p.body
              .split(/\n\s*\n/)
              .filter((para) => para.trim())
              .map((para, i) => (
                <p key={i} className="mb-3.5 whitespace-pre-line text-[13.5px] leading-[1.75] text-slate-600">
                  {para.trim()}
                </p>
              ))}
            <div className="my-6">
              <div className={cn("inline-block rounded-md border px-5 py-2.5", tone.chip)}>
                <span className={cn("font-mono text-[12.5px]", tone.text)}>Open {sender} →</span>
              </div>
            </div>
            <div className="border-t border-line pt-4">
              <p className="text-[11px] leading-normal text-muted">
                You&apos;re receiving this because you signed up for {sender}.{" "}
                <span className="underline">Unsubscribe</span>
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <MetaTile label="Subject line B (A/B test)">{p.subject_line_b}</MetaTile>
        <MetaTile label="Send timing">{p.send_time_note}</MetaTile>
        <MetaTile label="Who receives this" wide>
          {p.segment_note}
        </MetaTile>
      </div>
    </div>
  );
}

export const EmailCampaignCard = memo(function EmailCampaignCard({
  item,
  index,
  sender,
  copied,
  onCopy,
  onDelete,
}: {
  item: CreativeAsset<EmailCampaignPayload>;
  index: number;
  sender: string;
  copied: boolean;
  onCopy: (item: CreativeAsset<EmailCampaignPayload>) => void;
  onDelete: (item: CreativeAsset<EmailCampaignPayload>) => void;
}) {
  const [view, setView] = useState<"preview" | "raw">("preview");
  const p = item.payload;
  const tone = CAMPAIGN_TYPE_TONE[p.campaign_type] ?? CAMPAIGN_TYPE_TONE.update;
  return (
    <KitCard
      index={index}
      badge={
        <span
          className={cn(
            "inline-block rounded border px-2 py-0.5 font-mono text-[9.5px] uppercase tracking-[0.05em]",
            tone.chip,
            tone.text
          )}
        >
          {campaignTypeLabel(p.campaign_type)}
        </span>
      }
      title={p.subject_line}
      subtitle={p.preview_text}
      onDelete={() => onDelete(item)}
      deleteLabel="Delete this campaign"
    >
      <div className="mt-3 flex gap-1" role="group" aria-label="View">
        {(
          [
            ["preview", "Preview"],
            ["raw", "Raw text"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            aria-pressed={view === id}
            onClick={() => setView(id)}
            className={cn(
              "rounded-[5px] border px-2.5 py-1 font-mono text-[10.5px] transition-colors",
              view === id ? "border-accent bg-accent/5 text-accent-text" : "border-line text-muted hover:text-ink"
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {view === "preview" ? (
        <EmailPreview p={p} sender={sender} />
      ) : (
        <div className="mt-4 space-y-3 motion-safe:animate-screen-in">
          <Block title="Full body">
            <p className="whitespace-pre-wrap text-[13px] leading-[1.7] text-slate-600">{p.body}</p>
          </Block>
          <div className="grid gap-2 sm:grid-cols-2">
            <Block title="Subject B">
              <div className="text-[12.5px] text-slate-600">{p.subject_line_b}</div>
            </Block>
            <Block title="Segment">
              <div className="text-[12.5px] text-slate-600">{p.segment_note}</div>
            </Block>
          </div>
          <Block title="Send timing">
            <div className="text-[12.5px] text-slate-600">{p.send_time_note}</div>
          </Block>
        </div>
      )}

      <div className="mt-4 flex items-center gap-2">
        <CopyButton copied={copied} onClick={() => onCopy(item)} icon={Mail} label="Copy campaign" />
      </div>
    </KitCard>
  );
});
