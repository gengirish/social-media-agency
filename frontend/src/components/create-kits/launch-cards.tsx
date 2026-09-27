"use client";

import { memo, useState, type ReactNode } from "react";
import { FileText, Mail, Rocket } from "lucide-react";
import type { CreativeAsset } from "@/lib/api-foundation";
import type { CommunityKitPayload, LaunchKitPayload, OutreachPitchPayload } from "@/lib/api-create-kits";
import { Button } from "@/components/ui/button";
import { AccentBadge, Block, CopyButton, KitCard } from "@/components/create-kits/kit-shared";

/** Product Hunt's tagline limit — the prompt asks for it; this shows when the model ignored it. */
export const PH_TAGLINE_LIMIT = 60;

export function launchKitCopyText(p: LaunchKitPayload): string {
  return `TAGLINE: ${p.tagline}\n\nPH DESCRIPTION: ${p.ph_description}\n\nMAKER COMMENT:\n${p.maker_comment}\n\nTIMING: ${p.launch_timing_note}\n\nPRESS SUBJECT: ${p.press_pitch_subject}\n\nPRESS BODY:\n${p.press_pitch_body}`;
}

export function communityKitCopyText(p: CommunityKitPayload): string {
  return `CHANNELS:\n${p.channel_structure.join("\n")}\n\nWELCOME:\n${p.welcome_message}\n\nPROMPTS:\n${p.engagement_prompts.join("\n")}\n\nEVENT TEMPLATE:\n${p.event_announcement_template}`;
}

export function outreachCopyText(p: OutreachPitchPayload): string {
  return `SUBJECT: ${p.subject}\n\n${p.pitch_body}\n\nASK: ${p.specific_ask}`;
}

const text = "text-[12.5px] text-slate-600";
const prose = "whitespace-pre-wrap text-[13px] leading-[1.65] text-slate-600";

interface CardProps<P> {
  item: CreativeAsset<P>;
  index: number;
  copied: boolean;
  onCopy: (item: CreativeAsset<P>) => void;
  onDelete: (item: CreativeAsset<P>) => void;
}

function Expandable({
  expanded,
  onToggle,
  moreLabel,
  copy,
  children,
}: {
  expanded: boolean;
  onToggle: () => void;
  moreLabel: string;
  copy: ReactNode;
  children: ReactNode;
}) {
  return (
    <>
      {expanded && <div className="mt-4 space-y-3 motion-safe:animate-screen-in">{children}</div>}
      <div className="mt-4 flex items-center gap-2">
        <Button size="sm" variant="secondary" onClick={onToggle} aria-expanded={expanded}>
          {expanded ? "Collapse" : moreLabel}
        </Button>
        {copy}
      </div>
    </>
  );
}

export const LaunchKitCard = memo(function LaunchKitCard({ item, index, copied, onCopy, onDelete }: CardProps<LaunchKitPayload>) {
  const [expanded, setExpanded] = useState(false);
  const p = item.payload;
  const over = p.tagline.length > PH_TAGLINE_LIMIT;
  return (
    <KitCard
      index={index}
      badge={
        <span className="flex flex-wrap items-center gap-2">
          <AccentBadge>Product Hunt tagline</AccentBadge>
          {over && (
            <span className="font-mono text-[10px] text-amber-700">
              {p.tagline.length}/{PH_TAGLINE_LIMIT} chars — over Product Hunt&apos;s limit
            </span>
          )}
          {p.prfaq_addressed && <span className="font-mono text-[10px] text-sky-700">Addresses PRFAQ weak spot</span>}
        </span>
      }
      title={p.tagline}
      subtitle={p.why_now_hook}
      onDelete={() => onDelete(item)}
      deleteLabel="Delete this launch kit"
    >
      <Expandable
        expanded={expanded}
        onToggle={() => setExpanded((v) => !v)}
        moreLabel="View full kit"
        copy={<CopyButton copied={copied} onClick={() => onCopy(item)} icon={Rocket} label="Copy kit" />}
      >
        <Block title="PH description">
          <div className={text}>{p.ph_description}</div>
        </Block>
        <Block title="Maker's first comment">
          <p className={prose}>{p.maker_comment}</p>
        </Block>
        <Block title="Launch timing">
          <div className={text}>{p.launch_timing_note}</div>
        </Block>
        <div className="space-y-2 border-t border-line pt-2">
          <Block title="Press pitch subject">
            <div className="text-[13px] text-ink">{p.press_pitch_subject}</div>
          </Block>
          <Block title="Press pitch body">
            <p className={prose}>{p.press_pitch_body}</p>
          </Block>
        </div>
      </Expandable>
    </KitCard>
  );
});

export const CommunityKitCard = memo(function CommunityKitCard({
  item,
  index,
  copied,
  onCopy,
  onDelete,
}: CardProps<CommunityKitPayload>) {
  const [expanded, setExpanded] = useState(false);
  const p = item.payload;
  return (
    <KitCard
      index={index}
      badge={<AccentBadge>Community kit</AccentBadge>}
      title={p.channel_structure[0]}
      subtitle={p.welcome_message}
      onDelete={() => onDelete(item)}
      deleteLabel="Delete this kit"
    >
      <Expandable
        expanded={expanded}
        onToggle={() => setExpanded((v) => !v)}
        moreLabel="View full kit"
        copy={<CopyButton copied={copied} onClick={() => onCopy(item)} icon={FileText} label="Copy kit" />}
      >
        <Block title="Channel structure">
          {p.channel_structure.map((c, i) => (
            <div key={i} className={text}>
              {c}
            </div>
          ))}
        </Block>
        <Block title="Engagement prompts">
          {p.engagement_prompts.map((c, i) => (
            <div key={i} className={text}>
              {i + 1}. {c}
            </div>
          ))}
        </Block>
        <Block title="Event/AMA template">
          <p className={`${text} whitespace-pre-wrap`}>{p.event_announcement_template}</p>
        </Block>
        <Block title="Moderation note">
          <p className={text}>{p.moderation_note}</p>
        </Block>
      </Expandable>
    </KitCard>
  );
});

export const OutreachPitchCard = memo(function OutreachPitchCard({
  item,
  index,
  copied,
  onCopy,
  onDelete,
}: CardProps<OutreachPitchPayload>) {
  const [expanded, setExpanded] = useState(false);
  const p = item.payload;
  return (
    <KitCard
      index={index}
      badge={<AccentBadge>{p.target_type}</AccentBadge>}
      title={p.subject}
      subtitle={p.specific_ask}
      onDelete={() => onDelete(item)}
      deleteLabel="Delete this pitch"
    >
      <Expandable
        expanded={expanded}
        onToggle={() => setExpanded((v) => !v)}
        moreLabel="View full pitch"
        copy={<CopyButton copied={copied} onClick={() => onCopy(item)} icon={Mail} label="Copy pitch" />}
      >
        <Block title="Pitch body">
          <p className={prose}>{p.pitch_body}</p>
        </Block>
        <Block title="Economics note">
          <p className={text}>{p.economics_note}</p>
        </Block>
      </Expandable>
    </KitCard>
  );
});
