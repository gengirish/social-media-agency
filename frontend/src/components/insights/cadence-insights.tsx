"use client";

/*
 * Cadence's InsightsScreen for the active client: hero stats, Recommendations
 * (with the "How this works" threshold explainer), the Content Quality Signal,
 * the post pipeline and per-platform bars, then the Customer Advocacy agent.
 *
 * Every number is computed server-side from real rows (GET /insights/summary).
 * A ratio below its minimum sample arrives as null and renders "—" plus how much
 * more data it needs — never a placeholder.
 */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { CheckCircle2, Info } from "lucide-react";
import { insightsApi, type GatedRate, type InsightsSummary } from "@/lib/api-insights";
import type { ClientOverview } from "@/lib/api-foundation";
import { platformLabel } from "@/components/posts/platform";
import { buttonVariants } from "@/components/ui/button";
import { Eyebrow, Panel } from "@/components/ui/panel";
import { StatCard } from "@/components/ui/stat-card";
import { ErrorBanner } from "@/components/ui/feedback";
import { LoadingState } from "@/components/ui/empty-state";
import { InsightBar } from "@/components/insights/bars";
import { AdvocacyPanel } from "@/components/insights/advocacy-panel";
import { cn } from "@/lib/utils";

const PLATFORM_BAR: Record<string, string> = {
  linkedin: "bg-sky-500",
  twitter: "bg-slate-600",
  x: "bg-slate-600",
  facebook: "bg-blue-500",
  instagram: "bg-rose-500",
  tiktok: "bg-teal-500",
};

function rateValue(rate: GatedRate): string {
  return rate.value === null ? "—" : `${rate.value}%`;
}

function rateHint(rate: GatedRate, available: string): string {
  return rate.value === null
    ? `needs ${rate.needed} — ${rate.n} so far`
    : available;
}

export function RealDataBadge() {
  return (
    <span className="flex items-center gap-1.5 rounded-full border border-emerald-300 bg-emerald-50 px-3 py-1.5 text-[11px] font-medium text-emerald-700">
      <CheckCircle2 className="h-3 w-3" />
      100% real data — nothing here is invented
    </span>
  );
}

export function CadenceInsights({ client }: { client: ClientOverview }) {
  const [summary, setSummary] = useState<InsightsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [showThresholds, setShowThresholds] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      setSummary(await insightsApi.summary(client.id));
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [client.id]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading && !summary) return <LoadingState label="Computing insights" className="h-48" />;
  if (error || !summary) {
    return <ErrorBanner message="Couldn't load insights for this client." onRetry={() => void load()} />;
  }

  const s = summary;
  const funnel = [
    { label: "Pending", count: s.funnel.pending, bar: "bg-accent" },
    { label: "Approved", count: s.funnel.approved, bar: "bg-amber-400" },
    { label: "Scheduled", count: s.funnel.scheduled, bar: "bg-sky-500" },
    { label: "Published", count: s.funnel.published, bar: "bg-emerald-500" },
    { label: "Failed", count: s.funnel.failed, bar: "bg-red-500" },
  ];
  const maxFunnel = Math.max(1, ...funnel.map((f) => f.count));
  const connected = s.by_platform.filter((p) => p.connected);
  const maxPlatform = Math.max(1, ...connected.map((p) => p.count));
  const totalConnectedPosts = connected.reduce((sum, p) => sum + p.count, 0);
  const rates = s.quality_signal.rates;
  const maxEngagement = Math.max(1, ...s.engagement.by_platform.map((p) => p.avg_engagement));

  return (
    <div className="space-y-6">
      <p className="max-w-xl text-xs leading-relaxed text-muted">
        Everything below is computed from what has actually happened for {client.brand_name}. Follower
        counts and reach only appear once a connected platform has returned real metrics — they are
        never shown as placeholders.
      </p>

      {/* Hero stats */}
      <div className="grid grid-cols-2 gap-2.5 lg:grid-cols-4">
        <StatCard label="Posts in pipeline" value={s.total_posts} />
        <StatCard
          label="Publish success rate"
          value={rateValue(s.publish.success)}
          tone="accent"
          hint={rateHint(s.publish.success, `${s.publish.published} of ${s.publish.attempts}`)}
          delay={0.05}
        />
        <StatCard
          label="Clean approval rate"
          value={rateValue(s.moderation.clean)}
          tone="success"
          hint={rateHint(s.moderation.clean, `${s.moderation.flagged} of ${s.moderation.checks} flagged`)}
          delay={0.1}
        />
        <StatCard
          label="Published all-time"
          value={s.funnel.published}
          tone="info"
          hint={`Across ${s.connected_platforms.length} connected platform${s.connected_platforms.length === 1 ? "" : "s"}`}
          delay={0.15}
        />
      </div>

      {/* Recommendations */}
      <Panel className="p-5 motion-safe:animate-screen-in">
        <div className="flex items-center justify-between gap-3">
          <Eyebrow>Recommendations, from your real numbers</Eyebrow>
          <button
            type="button"
            onClick={() => setShowThresholds((v) => !v)}
            aria-expanded={showThresholds}
            className="flex items-center gap-1 font-mono text-[10px] text-muted hover:text-ink"
          >
            <Info className="h-3 w-3" /> How this works
          </button>
        </div>
        {showThresholds && (
          <div className="mt-2.5 rounded-md border border-line bg-slate-500/5 p-3 motion-safe:animate-screen-in">
            <p className="text-[11px] leading-relaxed text-muted">
              Every recommendation here needs a real minimum sample before it fires — never a conclusion
              from one or two data points. Below a threshold nothing shows — not because things look fine,
              but because there isn&apos;t enough real data yet to say either way.
            </p>
            <ul className="mt-2 space-y-1.5">
              {s.thresholds.map((t) => (
                <li key={t.id} className="flex items-start justify-between gap-3 text-[11px] text-muted">
                  <span>{t.rule}</span>
                  <span
                    className={cn(
                      "shrink-0 font-mono tabular-nums",
                      t.status === "evaluated" ? "text-emerald-700" : "text-muted"
                    )}
                  >
                    {t.status === "evaluated" ? "enough data" : `${t.have}/${t.needed} so far`}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {s.recommendations.length === 0 ? (
          <p className="mt-3 text-xs leading-relaxed text-muted">
            Nothing to flag yet — either everything looks healthy, or there isn&apos;t enough activity yet to
            draw a real conclusion from ({totalConnectedPosts} post{totalConnectedPosts === 1 ? "" : "s"} on
            connected platforms so far). Keep creating and check back.
          </p>
        ) : (
          <div className="mt-3 space-y-2.5">
            {s.recommendations.map((rec, i) => (
              <div
                key={rec.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-line bg-slate-500/5 p-3 motion-safe:animate-chip-in"
                style={{ animationDelay: `${i * 0.04}s` }}
              >
                <p className="text-[12.5px] leading-normal text-slate-600">{rec.text}</p>
                {rec.href && rec.action_label && (
                  <Link href={rec.href} className={cn(buttonVariants({ variant: "secondary", size: "sm" }), "shrink-0")}>
                    {rec.action_label}
                  </Link>
                )}
              </div>
            ))}
          </div>
        )}
      </Panel>

      {/* Content quality signal (Cadence §6 H2) */}
      <Panel className="p-5 motion-safe:animate-screen-in" style={{ animationDelay: "0.02s" }}>
        <Eyebrow>Content quality signal, from real outcomes</Eyebrow>
        <p className="mb-3 mt-2 max-w-2xl text-xs leading-relaxed text-muted">
          No LLM call here either — just what actually happened to what got drafted: approved as-is,
          edited before approval, or rejected. Real feedback on what&apos;s working, per platform — a
          platform needs at least {s.min_sample} real outcomes before it shows up here.
        </p>
        <div className="mb-4 grid gap-2 sm:grid-cols-3">
          <RateChip label="Approved without edits" rate={rates.approved_without_edit} />
          <RateChip label="Moderation flag rate" rate={rates.moderation_flag_rate} />
          <RateChip label="Failed-publish rate" rate={rates.failed_publish_rate} />
        </div>
        {s.quality_signal.rows.length === 0 ? (
          <p className="text-xs text-muted">
            Not enough approve/edit/reject history yet on any platform — check back after reviewing a few
            more posts.
          </p>
        ) : (
          <div className="space-y-2.5">
            {s.quality_signal.rows.map((row) => (
              <div key={row.platform} className="flex flex-wrap items-center gap-3">
                <span className="w-24 shrink-0 text-xs text-slate-600">{platformLabel(row.platform)}</span>
                <div
                  className="flex h-2 min-w-[120px] flex-1 overflow-hidden rounded bg-line"
                  role="img"
                  aria-label={`${platformLabel(row.platform)}: ${row.kept_pct}% kept as-is, ${row.edited_pct}% edited, ${row.discarded_pct}% rejected`}
                >
                  {row.kept_pct > 0 && <div className="bg-emerald-500" style={{ width: `${row.kept_pct}%` }} />}
                  {row.edited_pct > 0 && <div className="bg-accent" style={{ width: `${row.edited_pct}%` }} />}
                  {row.discarded_pct > 0 && <div className="bg-red-500" style={{ width: `${row.discarded_pct}%` }} />}
                </div>
                <span className="w-full shrink-0 font-mono text-[10.5px] text-muted sm:w-56">
                  {row.kept_pct}% kept · {row.edited_pct}% edited · {row.discarded_pct}% rejected
                </span>
              </div>
            ))}
          </div>
        )}
      </Panel>

      {/* Pipeline + platforms */}
      <div className="grid gap-4 md:grid-cols-2">
        <Panel className="p-5 motion-safe:animate-screen-in" style={{ animationDelay: "0.04s" }}>
          <Eyebrow>Post pipeline</Eyebrow>
          <div className="mt-4 space-y-3">
            {funnel.map((f) => (
              <InsightBar key={f.label} label={f.label} value={f.count} max={maxFunnel} barClass={f.bar} />
            ))}
          </div>
        </Panel>
        <Panel className="p-5 motion-safe:animate-screen-in" style={{ animationDelay: "0.08s" }}>
          <Eyebrow>Posts by platform</Eyebrow>
          {connected.length === 0 ? (
            <div className="mt-3 text-xs leading-normal text-muted">
              No accounts connected yet — connect one in Setup to see per-platform breakdowns.
              <br />
              <Link href="/setup/accounts" className="mt-1.5 inline-block text-[11.5px] text-accent-text underline">
                Go to Setup
              </Link>
            </div>
          ) : (
            <div className="mt-4 space-y-3">
              {connected.map((p) => (
                <InsightBar
                  key={p.platform}
                  label={platformLabel(p.platform)}
                  value={p.count}
                  max={maxPlatform}
                  barClass={PLATFORM_BAR[p.platform] ?? "bg-slate-400"}
                />
              ))}
            </div>
          )}
        </Panel>
      </div>

      {/* Engagement — only from metrics platforms actually returned */}
      <Panel className="p-5 motion-safe:animate-screen-in" style={{ animationDelay: "0.1s" }}>
        <Eyebrow>Engagement, as reported by the platforms</Eyebrow>
        {s.engagement.status === "unavailable" ? (
          <p className="mt-3 text-xs leading-relaxed text-muted">
            No platform has returned metrics for this client&apos;s published posts yet. Once a connected
            account reports engagement for a post, the real per-platform average appears here.
          </p>
        ) : (
          <div className="mt-4 space-y-3">
            {s.engagement.by_platform.map((p) => (
              <InsightBar
                key={p.platform}
                label={`${platformLabel(p.platform)} · avg per post (${p.posts} measured)`}
                value={p.avg_engagement}
                max={maxEngagement}
                barClass={PLATFORM_BAR[p.platform] ?? "bg-slate-400"}
              />
            ))}
          </div>
        )}
      </Panel>

      <AdvocacyPanel client={client} publishedCount={s.funnel.published} />
    </div>
  );
}

function RateChip({ label, rate }: { label: string; rate: GatedRate }) {
  const insufficient = rate.value === null;
  return (
    <div className="rounded-md border border-line bg-canvas/40 px-3 py-2.5">
      <div className={cn("font-display text-xl font-semibold tabular-nums", insufficient ? "text-slate-400" : "text-ink")}>
        {insufficient ? "—" : `${rate.value}%`}
      </div>
      <div className="mt-0.5 text-[11px] text-muted">{label}</div>
      <div className="mt-0.5 font-mono text-[10px] text-muted">
        {insufficient ? `Not enough data yet — needs ${rate.needed}, have ${rate.n}` : `${rate.count} of ${rate.n}`}
      </div>
    </div>
  );
}
