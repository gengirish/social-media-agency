"use client";

import Link from "next/link";
import { CheckCircle2, PenLine } from "lucide-react";
import type { ReactNode } from "react";
import { Eyebrow, Panel } from "@/components/ui/panel";
import { cn } from "@/lib/utils";
import { platformLabel, platformTone } from "./platform";

/** Cadence's UsageMeter: generations this period, from the subscription — never guessed. */
export function UsageMeter({
  used,
  limit,
  plan,
  delay = 0,
}: {
  used: number | null;
  limit: number | null;
  plan: string | null;
  delay?: number;
}) {
  if (used == null || limit == null || limit <= 0) {
    return (
      <div className="rounded-lg border border-line bg-panel/70 px-4 py-3 font-mono text-[10.5px] text-muted">
        Generation usage unavailable
      </div>
    );
  }
  const pct = Math.min(100, Math.round((used / limit) * 100));
  const near = pct >= 80;
  return (
    <div
      className={cn(
        "rounded-lg border bg-panel/70 px-4 py-3 backdrop-blur-xl motion-safe:animate-count-up",
        near ? "border-amber-300" : "border-line"
      )}
      style={delay ? { animationDelay: `${delay}s` } : undefined}
    >
      <div className="flex items-center justify-between">
        <span className="font-mono text-[10px] uppercase tracking-wider text-muted">
          {plan ? `${plan.charAt(0).toUpperCase()}${plan.slice(1)} plan` : "Plan"}
        </span>
        <span className={cn("font-mono text-[10.5px]", near ? "text-accent-text" : "text-muted")}>
          {used}/{limit} generations
        </span>
      </div>
      <div className="mt-2 h-1 overflow-hidden rounded-full bg-slate-500/15">
        <div
          className={cn("h-full transition-[width] duration-500", near ? "bg-accent" : "bg-sky-500")}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="mt-1 flex items-center justify-between font-mono text-[10px] text-muted">
        <span>Resets each billing period</span>
        {near && (
          <Link href="/pricing" className="text-accent-text underline">
            Upgrade →
          </Link>
        )}
      </div>
    </div>
  );
}

/** Cadence's compact stat row: icon, mono number, mono caption. Real counts only. */
export function MiniStat({
  icon,
  label,
  value,
  delay = 0,
}: {
  icon: ReactNode;
  label: string;
  value: number | null;
  delay?: number;
}) {
  return (
    <div
      className="flex items-center gap-3 rounded-lg border border-line bg-panel/70 px-4 py-3 backdrop-blur-xl motion-safe:animate-count-up"
      style={delay ? { animationDelay: `${delay}s` } : undefined}
    >
      <span className="flex h-8 w-8 items-center justify-center rounded-md border border-line text-accent-text">{icon}</span>
      <div>
        <div className={cn("font-mono text-[17px]", value == null ? "text-slate-400" : "text-ink")}>
          {value ?? "—"}
        </div>
        <div className="font-mono text-[10px] tracking-wider text-muted">{label}</div>
      </div>
    </div>
  );
}

/** Cadence's AccountChip, read-only: connecting happens under Setup › Accounts. */
export function AccountChip({ platform, connected }: { platform: string; connected: boolean }) {
  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-md border px-3 py-2 backdrop-blur-xl",
        connected ? "border-emerald-300 bg-emerald-50/60" : "border-line bg-panel/50"
      )}
    >
      <span
        className={cn(
          "flex h-5 w-5 items-center justify-center rounded-full border",
          connected ? "border-emerald-500 motion-safe:animate-ring-pulse" : "border-slate-300"
        )}
      >
        <span aria-hidden className={cn("h-2 w-2 rounded-full", connected ? platformTone(platform).dot : "bg-slate-300")} />
      </span>
      <span className={cn("font-mono text-[11.5px]", connected ? "text-ink" : "text-muted")}>{platformLabel(platform)}</span>
      <span className="ml-auto font-mono text-[10px] text-muted">{connected ? "connected" : "—"}</span>
    </div>
  );
}

/** Cadence's "Product profile" card → the active client's brand profile. */
export function ClientProfileCard({
  name,
  website,
  audience,
  voice,
  hasProfile,
}: {
  name: string;
  website: string | null;
  audience: string | null;
  voice: string | null;
  hasProfile: boolean;
}) {
  return (
    <Panel dashed className="p-5 motion-safe:animate-screen-in">
      <div className="flex items-center justify-between">
        <Eyebrow>Client profile</Eyebrow>
        <Link href="/setup/profile" aria-label="Edit client profile" title="Edit" className="text-muted hover:text-ink">
          <PenLine className="h-3 w-3" />
        </Link>
      </div>
      <h2 className="mt-2 truncate font-mono text-base text-ink">{name}</h2>
      {website && <p className="truncate font-mono text-[11px] text-muted">{website.replace(/^https?:\/\//, "")}</p>}
      <div className="mt-3 space-y-2">
        <div>
          <div className="font-mono text-[9.5px] uppercase tracking-[0.1em] text-muted">Audience</div>
          <div className="mt-0.5 text-[12.5px] text-slate-600">{audience || "Not set"}</div>
        </div>
        <div>
          <div className="font-mono text-[9.5px] uppercase tracking-[0.1em] text-muted">Voice</div>
          <div className="mt-0.5 line-clamp-3 text-[12.5px] text-slate-600">{voice || "Not set"}</div>
        </div>
      </div>
      <div
        className={cn(
          "mt-4 flex items-center gap-1.5 font-mono text-[10.5px]",
          hasProfile ? "text-emerald-600" : "text-muted"
        )}
      >
        <CheckCircle2 className="h-3 w-3" />
        {hasProfile ? "Profile live" : "No brand profile yet"}
      </div>
    </Panel>
  );
}
