"use client";

import type { ComponentType } from "react";
import { AtSign, CheckCircle2, Linkedin, Mail, MessageSquareReply, Twitter } from "lucide-react";
import type { InboxItem, InboxItemType } from "@/lib/api-inbox";
import { cn } from "@/lib/utils";

/** Cadence's TYPE_META. */
export const TYPE_META: Record<InboxItemType, { label: string; icon: ComponentType<{ className?: string }> }> = {
  mention: { label: "Mention", icon: AtSign },
  comment: { label: "Comment", icon: MessageSquareReply },
  dm: { label: "DM", icon: Mail },
};

const PLATFORM_ICON: Record<string, ComponentType<{ className?: string }>> = {
  twitter: Twitter,
  linkedin: Linkedin,
};

const PLATFORM_ICON_TONE: Record<string, string> = {
  twitter: "text-ink",
  linkedin: "text-sky-600",
};

export function PlatformGlyph({ platform, size = "sm" }: { platform: string; size?: "sm" | "md" }) {
  const Icon = PLATFORM_ICON[platform] ?? AtSign;
  return (
    <span
      aria-hidden
      className={cn(
        "flex shrink-0 items-center justify-center border border-line",
        size === "md" ? "h-8 w-8 rounded-lg" : "h-5 w-5 rounded"
      )}
    >
      <Icon className={cn(size === "md" ? "h-4 w-4" : "h-2.5 w-2.5", PLATFORM_ICON_TONE[platform] ?? "text-muted")} />
    </span>
  );
}

/** "12m", "3h", "4d" — Cadence's compact list time. Empty when the platform gave no time. */
export function shortAgo(iso: string | null, now = Date.now()): string {
  if (!iso) return "";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "";
  const s = Math.max(0, Math.round((now - t) / 1000));
  if (s < 60) return "now";
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  if (s < 86400 * 30) return `${Math.floor(s / 86400)}d`;
  return new Date(t).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function InboxListItem({
  item,
  active,
  onClick,
  delay,
}: {
  item: InboxItem;
  active: boolean;
  onClick: () => void;
  delay: number;
}) {
  const typeMeta = TYPE_META[item.type];
  const TypeIcon = typeMeta.icon;
  const unread = !item.read && !item.handled;
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={active ? "true" : undefined}
      className={cn(
        "w-full rounded-[9px] border px-3 py-3 text-left transition-all duration-200 motion-safe:animate-screen-in",
        active ? "border-accent bg-accent/10" : "border-line bg-panel/70 hover:border-slate-300",
        item.handled && "opacity-[0.55]"
      )}
      style={{ animationDelay: `${delay}s` }}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-1.5">
          <PlatformGlyph platform={item.platform} />
          <span className="truncate text-xs font-medium text-ink">{item.author.name}</span>
          {unread && (
            <span className="inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-accent" aria-label="Unread" />
          )}
        </div>
        <span className="shrink-0 font-mono text-[9.5px] text-muted">{shortAgo(item.created_at)}</span>
      </div>
      <div className="mt-1.5 flex items-center gap-1 text-[10px] uppercase tracking-wider text-muted">
        <TypeIcon className="h-2.5 w-2.5" /> {typeMeta.label}
      </div>
      <p className="mt-1.5 truncate text-xs text-slate-600">{item.text}</p>
      {item.handled && (
        <div className="mt-1.5 flex items-center gap-1 text-[10px] font-medium text-emerald-600">
          <CheckCircle2 className="h-2.5 w-2.5" /> Handled
        </div>
      )}
    </button>
  );
}
