"use client";

import { useEffect, useState } from "react";
import { api, type DashboardStats } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/panel";
import { SectionCard } from "@/components/ui/section-card";
import { StatCard } from "@/components/ui/stat-card";
import { Field, Input, Select } from "@/components/ui/field";
import { EmptyState, LoadingState, Notice } from "@/components/ui/empty-state";
import { SegmentedTabs } from "@/components/ui/tabs";
import {
  BarChart3,
  Users,
  Layers,
  Bot,
  FileText,
  TrendingUp,
  Clock,
} from "lucide-react";

type AnalyticsTab = "overview" | "trends" | "benchmarks";

interface TrendItem {
  topic: string;
  url?: string;
  source?: string | null;
  platform?: string | null;
  published_date?: string | null;
  recency_days?: number | null;
}

interface TrendsResponse {
  status?: string;
  reason?: string;
  source?: string;
  provenance?: string;
  fetched_at?: string;
  items?: TrendItem[];
}

interface CrossInsight {
  platform: string;
  avg_performance: number;
  content_count: number;
  insight: string;
}

interface IndustryBenchmark {
  industry: string;
  status?: "available" | "unavailable";
  reason?: string;
  avg_impressions: number | null;
  avg_engagement: number | null;
  avg_clicks: number | null;
  avg_likes: number | null;
  sample_size: number;
  contributing_orgs?: number;
}

const TREND_PLATFORMS = [
  { value: "", label: "All platforms" },
  { value: "twitter", label: "X / Twitter" },
  { value: "linkedin", label: "LinkedIn" },
  { value: "instagram", label: "Instagram" },
  { value: "facebook", label: "Facebook" },
];

export default function AnalyticsPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [tab, setTab] = useState<AnalyticsTab>("overview");
  const [trends, setTrends] = useState<TrendItem[]>([]);
  const [trendsLoading, setTrendsLoading] = useState(false);
  const [trendsError, setTrendsError] = useState("");
  const [trendsUnavailable, setTrendsUnavailable] = useState("");
  const [trendsProvenance, setTrendsProvenance] = useState("");
  const [trendPlatform, setTrendPlatform] = useState("");

  const [crossLoading, setCrossLoading] = useState(false);
  const [crossError, setCrossError] = useState("");
  const [insights, setInsights] = useState<CrossInsight[]>([]);
  const [benchmarks, setBenchmarks] = useState<IndustryBenchmark | null>(null);
  const [industryDraft, setIndustryDraft] = useState("");
  const [appliedIndustry, setAppliedIndustry] = useState<string | undefined>(undefined);

  useEffect(() => {
    api
      .getStats()
      .then(setStats)
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : "Failed to load stats")
      )
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (tab !== "trends") return;
    setTrendsLoading(true);
    setTrendsError("");
    setTrendsUnavailable("");
    setTrendsProvenance("");
    api
      .getTrends(trendPlatform || undefined)
      .then((data) => {
        const payload = data as TrendsResponse;
        if (payload.status === "unavailable") {
          setTrends([]);
          setTrendsUnavailable(payload.reason || "Trend data source is not available.");
          return;
        }
        setTrends(payload.items || []);
        setTrendsProvenance(payload.provenance || "");
      })
      .catch((e: unknown) =>
        setTrendsError(e instanceof Error ? e.message : "Failed to load trends")
      )
      .finally(() => setTrendsLoading(false));
  }, [tab, trendPlatform]);

  useEffect(() => {
    if (tab !== "benchmarks") return;
    setCrossLoading(true);
    setCrossError("");
    api
      .getCrossLearning(appliedIndustry)
      .then((data) => {
        setInsights((data.insights || []) as CrossInsight[]);
        const b = data.benchmarks;
        setBenchmarks(
          b && typeof b === "object" && b !== null && "industry" in b
            ? (b as IndustryBenchmark)
            : null
        );
      })
      .catch((e: unknown) =>
        setCrossError(e instanceof Error ? e.message : "Failed to load cross-learning data")
      )
      .finally(() => setCrossLoading(false));
  }, [tab, appliedIndustry]);


  const header = (
    <PageHeader
      eyebrow="Insights"
      title="Analytics"
      description="Campaign performance and platform insights"
    />
  );

  if (loading) {
    return (
      <div className="space-y-8">
        {header}
        <LoadingState label="Loading stats" />
      </div>
    );
  }

  if (error || !stats) {
    return (
      <div className="space-y-8">
        {header}
        <Notice tone="danger">{error || "No data available"}</Notice>
      </div>
    );
  }

  const kpis = [
    { label: "Total Clients", value: stats.total_clients, icon: Users },
    { label: "Campaigns", value: stats.total_campaigns, icon: Layers },
    { label: "Content Pieces", value: stats.total_content_pieces, icon: FileText },
    { label: "Agent Runs", value: stats.total_agent_runs, icon: Bot },
  ];

  const nonDraft = Math.max(0, stats.total_content_pieces - stats.content_drafts);
  const contentBreakdown = [
    { label: "Draft", value: stats.content_drafts, color: "bg-accent" },
    { label: "Approved / scheduled / published", value: nonDraft, color: "bg-emerald-500" },
  ];
  const totalContent = stats.total_content_pieces || 1;

  const tabs: { id: AnalyticsTab; label: string }[] = [
    { id: "overview", label: "Overview" },
    { id: "trends", label: "Trends" },
    { id: "benchmarks", label: "Benchmarks" },
  ];

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        {header}
        <SegmentedTabs label="Analytics views" items={tabs} value={tab} onChange={setTab} />
      </div>

      {tab === "overview" && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {kpis.map((kpi, i) => (
              <StatCard
                key={kpi.label}
                label={kpi.label}
                value={kpi.value.toLocaleString()}
                icon={kpi.icon}
                delay={i * 0.05}
              />
            ))}
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <SectionCard
              eyebrow="Content"
              title="Content Pipeline"
              description="Draft vs all other statuses (approved, scheduled, published)."
              delay={0.1}
            >
              <div className="space-y-4">
                {contentBreakdown.map((item) => (
                  <div key={item.label}>
                    <div className="mb-1.5 flex items-center justify-between text-sm">
                      <span className="text-muted">{item.label}</span>
                      <span className="font-mono text-xs font-medium text-ink">{item.value}</span>
                    </div>
                    <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-200">
                      <div
                        className={`h-full rounded-full ${item.color} transition-all duration-700`}
                        style={{ width: `${Math.round((item.value / totalContent) * 100)}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </SectionCard>

            <SectionCard eyebrow="Campaigns" title="Campaign Status" delay={0.15}>
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-lg border border-accent/40 bg-accent/10 p-4">
                  <p className="font-display text-3xl font-semibold tabular-nums text-accent-text">{stats.campaigns_running}</p>
                  <p className="mt-1 text-xs text-muted">Running</p>
                </div>
                <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4">
                  <p className="font-display text-3xl font-semibold tabular-nums text-emerald-700">
                    {stats.total_campaigns - stats.campaigns_running}
                  </p>
                  <p className="mt-1 text-xs text-muted">Completed</p>
                </div>
              </div>
              <div className="mt-3 flex items-center gap-2 rounded-lg border border-line bg-canvas/40 px-3 py-2 text-sm text-muted">
                <TrendingUp className="h-4 w-4 shrink-0 text-accent-text" />
                <span>{stats.total_agent_runs} total agent executions across all campaigns</span>
              </div>
            </SectionCard>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <SectionCard
              eyebrow="Portfolio"
              title="Campaign activity"
              description="Share of campaigns currently running vs the rest of your portfolio (from live stats, not a dated timeline)."
              delay={0.2}
            >
              {stats.total_campaigns > 0 ? (
                <>
                  <div className="mb-2 flex h-2 w-full gap-0.5 overflow-hidden rounded-full bg-slate-200">
                    <div
                      className="h-full rounded-full bg-accent transition-all duration-700"
                      style={{
                        width: `${Math.round((stats.campaigns_running / stats.total_campaigns) * 100)}%`,
                      }}
                    />
                    <div
                      className="h-full rounded-full bg-slate-400 transition-all duration-700"
                      style={{
                        width: `${Math.round(
                          ((stats.total_campaigns - stats.campaigns_running) / stats.total_campaigns) * 100
                        )}%`,
                      }}
                    />
                  </div>
                  <div className="flex justify-between font-mono text-[11px] text-muted">
                    <span className="flex items-center gap-1.5">
                      <span className="h-2 w-2 rounded-full bg-accent" />
                      Running: {stats.campaigns_running}
                    </span>
                    <span className="flex items-center gap-1.5">
                      <span className="h-2 w-2 rounded-full bg-slate-400" />
                      Other: {stats.total_campaigns - stats.campaigns_running}
                    </span>
                  </div>
                </>
              ) : (
                <p className="text-sm text-muted">Create a campaign to see activity distribution.</p>
              )}
            </SectionCard>

            <SectionCard eyebrow="Agents" title="Agent run metrics" delay={0.25}>
              <dl className="divide-y divide-line">
                <div className="flex items-center justify-between pb-3">
                  <dt className="text-sm text-muted">Total runs</dt>
                  <dd className="font-display text-xl font-semibold tabular-nums text-ink">
                    {stats.total_agent_runs.toLocaleString()}
                  </dd>
                </div>
                <div className="flex items-center justify-between py-3">
                  <dt className="text-sm text-muted">Avg runs per campaign</dt>
                  <dd className="font-display text-xl font-semibold tabular-nums text-ink">
                    {stats.total_campaigns > 0
                      ? (stats.total_agent_runs / stats.total_campaigns).toFixed(1)
                      : "—"}
                  </dd>
                </div>
                <div className="flex items-center justify-between pt-3">
                  <dt className="text-sm text-muted">Content in draft</dt>
                  <dd className="font-display text-xl font-semibold tabular-nums text-ink">
                    {stats.total_content_pieces > 0
                      ? `${Math.round((stats.content_drafts / stats.total_content_pieces) * 100)}%`
                      : "—"}
                  </dd>
                </div>
              </dl>
            </SectionCard>
          </div>

          {/* No code path ever populates this panel — there is no per-platform
              analytics view in the dashboard. Say so instead of implying that
              connecting an account unlocks it. */}
          <div className="rounded-xl border border-dashed border-slate-300 bg-panel/50 p-5 backdrop-blur-xl sm:p-6">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <h3 className="font-display font-semibold text-ink">Platform Insights</h3>
              <span className="rounded-full border border-amber-300 bg-amber-50 px-2 py-0.5 font-mono text-[11px] font-medium text-amber-800">
                Not available yet
              </span>
            </div>
            <p className="max-w-3xl text-sm text-muted">
              Per-platform engagement, ROI, and optimal-posting-time breakdowns are not built yet.
              Live metrics for individual posts are fetched from connected accounts and shown on
              each content piece; there is no roll-up view here.
            </p>
            <div className="mt-4 flex flex-wrap gap-4 font-mono text-[11px] text-muted">
              <div className="flex items-center gap-1">
                <TrendingUp className="h-3.5 w-3.5" /> Engagement
              </div>
              <div className="flex items-center gap-1">
                <BarChart3 className="h-3.5 w-3.5" /> ROI
              </div>
              <div className="flex items-center gap-1">
                <Clock className="h-3.5 w-3.5" /> Posting Times
              </div>
            </div>
          </div>
        </div>
      )}

      {tab === "trends" && (
        <div className="space-y-4">
          <SectionCard bodyClassName="flex flex-wrap items-end gap-4" className="p-4 sm:p-5">
            <Field label="Platform" htmlFor="trend-platform" className="w-full sm:w-56">
              <Select id="trend-platform" value={trendPlatform} onChange={(e) => setTrendPlatform(e.target.value)}>
                {TREND_PLATFORMS.map((p) => (
                  <option key={p.value || "all"} value={p.value}>
                    {p.label}
                  </option>
                ))}
              </Select>
            </Field>
            <p className="pb-2.5 text-sm text-muted">
              Live web results from the Exa search API. Every row links to its source.
            </p>
          </SectionCard>

          {trendsLoading ? (
            <LoadingState label="Fetching trends" className="h-48" />
          ) : trendsError ? (
            <Notice tone="danger">{trendsError}</Notice>
          ) : trendsUnavailable ? (
            <Notice tone="warning" title={<>Not available — {trendsUnavailable}</>}>
              No trend data is shown rather than estimated topics. Once a key is configured, this
              tab lists real, source-linked results.
            </Notice>
          ) : trends.length === 0 ? (
            <EmptyState icon={TrendingUp} title="No trend rows returned." />
          ) : (
            <>
              <div className="overflow-x-auto rounded-xl border border-line bg-panel/70 shadow-soft backdrop-blur-xl">
                <table className="w-full min-w-[560px] text-left text-sm">
                  <thead className="border-b border-line font-mono text-[11px] text-muted">
                    <tr>
                      <th className="px-4 py-3 font-medium">Topic</th>
                      <th className="px-4 py-3 font-medium">Platform</th>
                      <th className="px-4 py-3 font-medium">Published</th>
                      <th className="px-4 py-3 font-medium">Source</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {trends.map((row, i) => (
                      <tr
                        key={`${row.topic}-${row.url ?? ""}-${i}`}
                        className="transition-colors hover:bg-slate-500/5"
                      >
                        <td className="px-4 py-3 font-medium text-ink">
                          {row.url ? (
                            <a
                              href={row.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-accent-text hover:underline"
                            >
                              {row.topic}
                            </a>
                          ) : (
                            row.topic
                          )}
                        </td>
                        <td className="px-4 py-3 capitalize text-muted">
                          {row.platform ?? "All platforms"}
                        </td>
                        <td className="px-4 py-3 font-mono text-xs text-muted">
                          {typeof row.recency_days === "number"
                            ? row.recency_days === 0
                              ? "Today"
                              : `${row.recency_days}d ago`
                            : "—"}
                        </td>
                        <td className="px-4 py-3 text-muted">{row.source ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {trendsProvenance && (
                <p className="font-mono text-[11px] text-muted">{trendsProvenance}</p>
              )}
            </>
          )}
        </div>
      )}

      {tab === "benchmarks" && (
        <div className="space-y-4">
          <SectionCard
            eyebrow="Industry"
            title="Industry benchmarks"
            description="Compare your org against aggregated analytics snapshots for clients in the same industry (when data exists)."
          >
            <div className="flex flex-wrap items-end gap-3">
              <Field
                label={<>Industry (match client &quot;industry&quot; field)</>}
                htmlFor="benchmark-industry"
                className="w-full sm:w-72"
              >
                <Input
                  id="benchmark-industry"
                  value={industryDraft}
                  onChange={(e) => setIndustryDraft(e.target.value)}
                  placeholder="e.g. SaaS, Healthcare"
                />
              </Field>
              <Button
                className="py-2.5"
                onClick={() =>
                  setAppliedIndustry(industryDraft.trim() ? industryDraft.trim() : undefined)
                }
              >
                Load benchmarks
              </Button>
              <Button
                variant="secondary"
                className="py-2.5"
                onClick={() => {
                  setIndustryDraft("");
                  setAppliedIndustry(undefined);
                }}
              >
                Clear industry
              </Button>
            </div>

            {crossLoading ? (
              <LoadingState className="h-32" />
            ) : crossError ? (
              <Notice tone="danger" className="mt-4">{crossError}</Notice>
            ) : benchmarks && benchmarks.sample_size > 0 ? (
              <dl className="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-5">
                <BenchmarkStat label="Avg impressions" value={benchmarks.avg_impressions} />
                <BenchmarkStat label="Avg engagement" value={benchmarks.avg_engagement} />
                <BenchmarkStat label="Avg clicks" value={benchmarks.avg_clicks} />
                <BenchmarkStat label="Avg likes" value={benchmarks.avg_likes} />
                <BenchmarkStat
                  label="Sample size"
                  value={benchmarks.sample_size}
                  hint={benchmarks.contributing_orgs ? `across ${benchmarks.contributing_orgs} organisations` : undefined}
                />
              </dl>
            ) : (
              /* Show the server's own reason. It distinguishes "no data yet"
                 from the cross-org privacy floor, and only the first of those
                 is something the user can act on. */
              <p className="mt-4 text-sm text-amber-800">
                {benchmarks?.reason
                  ? benchmarks.reason
                  : appliedIndustry
                    ? "No benchmark rows for that industry yet. Try another industry or add analytics snapshots."
                    : "Enter an industry and click Load benchmarks, or rely on cross-campaign insights below."}
              </p>
            )}
          </SectionCard>

          <SectionCard
            eyebrow="Learning"
            title="Cross-campaign insights"
            description="Patterns from your org's highest-scoring content, grouped by platform."
            delay={0.05}
          >
            {crossLoading && insights.length === 0 ? (
              <LoadingState className="h-32" />
            ) : insights.length === 0 ? (
              <p className="text-sm text-muted">
                No scored content yet — publish or score content to populate insights.
              </p>
            ) : (
              <ul className="space-y-2.5">
                {insights.map((row) => (
                  <li key={row.platform} className="border-l-2 border-accent/60 py-1 pl-4">
                    <p className="text-sm font-medium capitalize text-ink">{row.platform}</p>
                    <p className="mt-1 text-sm text-muted">{row.insight}</p>
                    <p className="mt-1 font-mono text-[11px] text-muted">
                      Avg score {row.avg_performance} · {row.content_count} pieces
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </SectionCard>
        </div>
      )}
    </div>
  );
}

function BenchmarkStat({ label, value, hint }: { label: string; value: number | null; hint?: string }) {
  // `null` means the metric was not measured, which is not the same as zero —
  // the backend deliberately keeps SQL NULL rather than coercing to 0, so
  // rendering a 0 here would turn "no data" into a measurement.
  return (
    <div className="rounded-lg border border-line bg-canvas/40 p-4">
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="mt-1 font-display text-xl font-semibold tabular-nums text-ink">
        {value === null ? <span className="text-base font-medium text-muted">Not measured</span> : value}
      </dd>
      {hint && <dd className="mt-0.5 text-xs text-muted">{hint}</dd>}
    </div>
  );
}
