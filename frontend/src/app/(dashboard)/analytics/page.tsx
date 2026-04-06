"use client";

import { useEffect, useState } from "react";
import { api, type DashboardStats } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  BarChart3,
  Users,
  Layers,
  Bot,
  FileText,
  ArrowUpRight,
  Loader2,
  TrendingUp,
  Clock,
} from "lucide-react";

type AnalyticsTab = "overview" | "trends" | "benchmarks";

interface TrendItem {
  topic: string;
  volume: string;
  category: string;
  platform?: string;
}

interface CrossInsight {
  platform: string;
  avg_performance: number;
  content_count: number;
  insight: string;
}

interface IndustryBenchmark {
  industry: string;
  avg_impressions: number;
  avg_engagement: number;
  avg_clicks: number;
  avg_likes: number;
  sample_size: number;
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
    api
      .getTrends(trendPlatform || undefined)
      .then((data) => {
        const items = (data.items || []) as TrendItem[];
        setTrends(items);
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

  if (loading) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Analytics</h1>
          <p className="mt-1 text-slate-500">Campaign performance and platform insights</p>
        </div>
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
        </div>
      </div>
    );
  }

  if (error || !stats) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Analytics</h1>
          <p className="mt-1 text-slate-500">Campaign performance and platform insights</p>
        </div>
        <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-center text-red-700">
          {error || "No data available"}
        </div>
      </div>
    );
  }

  const kpis = [
    {
      label: "Total Clients",
      value: stats.total_clients,
      icon: Users,
      iconBg: "bg-indigo-50",
      iconClass: "text-indigo-600",
    },
    {
      label: "Campaigns",
      value: stats.total_campaigns,
      icon: Layers,
      iconBg: "bg-emerald-50",
      iconClass: "text-emerald-600",
    },
    {
      label: "Content Pieces",
      value: stats.total_content_pieces,
      icon: FileText,
      iconBg: "bg-amber-50",
      iconClass: "text-amber-600",
    },
    {
      label: "Agent Runs",
      value: stats.total_agent_runs,
      icon: Bot,
      iconBg: "bg-purple-50",
      iconClass: "text-purple-600",
    },
  ];

  const nonDraft = Math.max(0, stats.total_content_pieces - stats.content_drafts);
  const contentBreakdown = [
    { label: "Draft", value: stats.content_drafts, color: "bg-amber-500" },
    { label: "Approved / scheduled / published", value: nonDraft, color: "bg-emerald-500" },
  ];
  const totalContent = stats.total_content_pieces || 1;

  const tabs: { id: AnalyticsTab; label: string }[] = [
    { id: "overview", label: "Overview" },
    { id: "trends", label: "Trends" },
    { id: "benchmarks", label: "Benchmarks" },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Analytics</h1>
        <p className="mt-1 text-slate-500">Campaign performance and platform insights</p>
      </div>

      <div className="flex flex-wrap gap-2 border-b border-slate-200 pb-1">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={cn(
              "rounded-t-lg px-4 py-2 text-sm font-medium transition-colors",
              tab === t.id
                ? "bg-white text-indigo-700 shadow-sm ring-1 ring-slate-200"
                : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "overview" && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {kpis.map((kpi) => (
              <div
                key={kpi.label}
                className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
              >
                <div className="flex items-center justify-between">
                  <div className={`rounded-lg p-2 ${kpi.iconBg}`}>
                    <kpi.icon className={`h-5 w-5 ${kpi.iconClass}`} />
                  </div>
                  <ArrowUpRight className="h-4 w-4 text-slate-300" />
                </div>
                <div className="mt-3">
                  <p className="text-2xl font-bold text-slate-900">{kpi.value.toLocaleString()}</p>
                  <p className="text-sm text-slate-500">{kpi.label}</p>
                </div>
              </div>
            ))}
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
              <h3 className="mb-1 font-semibold text-slate-900">Content Pipeline</h3>
              <p className="mb-4 text-sm text-slate-500">
                Draft vs all other statuses (approved, scheduled, published).
              </p>
              <div className="space-y-3">
                {contentBreakdown.map((item) => (
                  <div key={item.label}>
                    <div className="mb-1 flex items-center justify-between text-sm">
                      <span className="text-slate-600">{item.label}</span>
                      <span className="font-medium text-slate-900">{item.value}</span>
                    </div>
                    <div className="h-2.5 w-full overflow-hidden rounded-full bg-slate-100">
                      <div
                        className={`h-full rounded-full ${item.color} transition-all`}
                        style={{ width: `${Math.round((item.value / totalContent) * 100)}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
              <h3 className="mb-4 font-semibold text-slate-900">Campaign Status</h3>
              <div className="grid grid-cols-2 gap-4">
                <div className="rounded-lg bg-indigo-50 p-4 text-center">
                  <p className="text-3xl font-bold text-indigo-700">{stats.campaigns_running}</p>
                  <p className="mt-1 text-sm text-indigo-600">Running</p>
                </div>
                <div className="rounded-lg bg-emerald-50 p-4 text-center">
                  <p className="text-3xl font-bold text-emerald-700">
                    {stats.total_campaigns - stats.campaigns_running}
                  </p>
                  <p className="mt-1 text-sm text-emerald-600">Completed</p>
                </div>
              </div>
              <div className="mt-4 flex items-center gap-2 rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-600">
                <TrendingUp className="h-4 w-4" />
                <span>{stats.total_agent_runs} total agent executions across all campaigns</span>
              </div>
            </div>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
              <h3 className="mb-1 font-semibold text-slate-900">Campaign activity</h3>
              <p className="mb-4 text-sm text-slate-500">
                Share of campaigns currently running vs the rest of your portfolio (from live stats, not a
                dated timeline).
              </p>
              {stats.total_campaigns > 0 ? (
                <>
                  <div className="mb-2 flex h-3 w-full overflow-hidden rounded-full bg-slate-100">
                    <div
                      className="h-full bg-indigo-500 transition-all"
                      style={{
                        width: `${Math.round((stats.campaigns_running / stats.total_campaigns) * 100)}%`,
                      }}
                    />
                    <div
                      className="h-full bg-slate-300 transition-all"
                      style={{
                        width: `${Math.round(
                          ((stats.total_campaigns - stats.campaigns_running) / stats.total_campaigns) * 100
                        )}%`,
                      }}
                    />
                  </div>
                  <div className="flex justify-between text-xs text-slate-500">
                    <span>Running: {stats.campaigns_running}</span>
                    <span>Other: {stats.total_campaigns - stats.campaigns_running}</span>
                  </div>
                </>
              ) : (
                <p className="text-sm text-slate-500">Create a campaign to see activity distribution.</p>
              )}
            </div>

            <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
              <h3 className="mb-4 font-semibold text-slate-900">Agent run metrics</h3>
              <dl className="space-y-4">
                <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                  <dt className="text-sm text-slate-600">Total runs</dt>
                  <dd className="text-lg font-semibold text-slate-900">
                    {stats.total_agent_runs.toLocaleString()}
                  </dd>
                </div>
                <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                  <dt className="text-sm text-slate-600">Avg runs per campaign</dt>
                  <dd className="text-lg font-semibold text-slate-900">
                    {stats.total_campaigns > 0
                      ? (stats.total_agent_runs / stats.total_campaigns).toFixed(1)
                      : "—"}
                  </dd>
                </div>
                <div className="flex items-center justify-between">
                  <dt className="text-sm text-slate-600">Content in draft</dt>
                  <dd className="text-lg font-semibold text-slate-900">
                    {stats.total_content_pieces > 0
                      ? `${Math.round((stats.content_drafts / stats.total_content_pieces) * 100)}%`
                      : "—"}
                  </dd>
                </div>
              </dl>
            </div>
          </div>

          <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
            <h3 className="mb-2 font-semibold text-slate-900">Platform Insights</h3>
            <p className="text-sm text-slate-500">
              Connect social platform accounts in Settings to see per-platform engagement metrics, optimal
              posting times, and content performance analytics.
            </p>
            <div className="mt-4 flex gap-4 text-sm text-slate-400">
              <div className="flex items-center gap-1">
                <TrendingUp className="h-4 w-4" /> Engagement
              </div>
              <div className="flex items-center gap-1">
                <BarChart3 className="h-4 w-4" /> ROI
              </div>
              <div className="flex items-center gap-1">
                <Clock className="h-4 w-4" /> Posting Times
              </div>
            </div>
          </div>
        </>
      )}

      {tab === "trends" && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <div>
              <label htmlFor="trend-platform" className="block text-xs font-medium text-slate-500">
                Platform
              </label>
              <select
                id="trend-platform"
                value={trendPlatform}
                onChange={(e) => setTrendPlatform(e.target.value)}
                className="mt-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900"
              >
                {TREND_PLATFORMS.map((p) => (
                  <option key={p.value || "all"} value={p.value}>
                    {p.label}
                  </option>
                ))}
              </select>
            </div>
            <p className="text-sm text-slate-500">
              Topic signals from the trends service (demo data until external feeds are connected).
            </p>
          </div>

          {trendsLoading ? (
            <div className="flex justify-center py-16">
              <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
            </div>
          ) : trendsError ? (
            <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
              {trendsError}
            </div>
          ) : trends.length === 0 ? (
            <p className="rounded-xl border border-slate-200 bg-white p-8 text-center text-slate-500 shadow-sm">
              No trend rows returned.
            </p>
          ) : (
            <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-slate-100 bg-slate-50 text-xs font-semibold uppercase text-slate-500">
                  <tr>
                    <th className="px-4 py-3">Topic</th>
                    <th className="px-4 py-3">Platform</th>
                    <th className="px-4 py-3">Volume</th>
                    <th className="px-4 py-3">Category</th>
                  </tr>
                </thead>
                <tbody>
                  {trends.map((row, i) => (
                    <tr key={`${row.topic}-${row.platform}-${i}`} className="border-b border-slate-50">
                      <td className="px-4 py-3 font-medium text-slate-900">{row.topic}</td>
                      <td className="px-4 py-3 capitalize text-slate-600">{row.platform ?? "—"}</td>
                      <td className="px-4 py-3 text-slate-600">{row.volume}</td>
                      <td className="px-4 py-3 text-slate-600">{row.category}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {tab === "benchmarks" && (
        <div className="space-y-6">
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <h3 className="text-lg font-semibold text-slate-900">Industry benchmarks</h3>
            <p className="mt-1 text-sm text-slate-500">
              Compare your org against aggregated analytics snapshots for clients in the same industry (when
              data exists).
            </p>
            <div className="mt-4 flex flex-wrap items-end gap-3">
              <div>
                <label htmlFor="benchmark-industry" className="block text-xs font-medium text-slate-500">
                  Industry (match client &quot;industry&quot; field)
                </label>
                <input
                  id="benchmark-industry"
                  value={industryDraft}
                  onChange={(e) => setIndustryDraft(e.target.value)}
                  placeholder="e.g. SaaS, Healthcare"
                  className="mt-1 w-64 rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-900"
                />
              </div>
              <button
                type="button"
                onClick={() =>
                  setAppliedIndustry(industryDraft.trim() ? industryDraft.trim() : undefined)
                }
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500"
              >
                Load benchmarks
              </button>
              <button
                type="button"
                onClick={() => {
                  setIndustryDraft("");
                  setAppliedIndustry(undefined);
                }}
                className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                Clear industry
              </button>
            </div>

            {crossLoading ? (
              <div className="mt-6 flex justify-center py-8">
                <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
              </div>
            ) : crossError ? (
              <p className="mt-4 text-sm text-red-600">{crossError}</p>
            ) : benchmarks && benchmarks.sample_size > 0 ? (
              <dl className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <BenchmarkStat label="Avg impressions" value={benchmarks.avg_impressions} />
                <BenchmarkStat label="Avg engagement" value={benchmarks.avg_engagement} />
                <BenchmarkStat label="Avg clicks" value={benchmarks.avg_clicks} />
                <BenchmarkStat label="Avg likes" value={benchmarks.avg_likes} />
                <div className="rounded-lg bg-slate-50 p-4">
                  <p className="text-xs text-slate-500">Sample size</p>
                  <p className="text-lg font-semibold text-slate-900">{benchmarks.sample_size}</p>
                </div>
              </dl>
            ) : (
              <p className="mt-4 text-sm text-amber-800">
                {appliedIndustry
                  ? "No benchmark rows for that industry yet. Try another industry or add analytics snapshots."
                  : "Enter an industry and click Load benchmarks, or rely on cross-campaign insights below."}
              </p>
            )}
          </div>

          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <h3 className="text-lg font-semibold text-slate-900">Cross-campaign insights</h3>
            <p className="mt-1 text-sm text-slate-500">
              Patterns from your org&apos;s highest-scoring content, grouped by platform.
            </p>
            {crossLoading && insights.length === 0 ? (
              <div className="mt-6 flex justify-center py-8">
                <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
              </div>
            ) : insights.length === 0 ? (
              <p className="mt-4 text-sm text-slate-500">
                No scored content yet — publish or score content to populate insights.
              </p>
            ) : (
              <ul className="mt-4 space-y-3">
                {insights.map((row) => (
                  <li
                    key={row.platform}
                    className="rounded-lg border border-slate-100 bg-slate-50/80 px-4 py-3"
                  >
                    <p className="text-sm font-medium capitalize text-slate-900">{row.platform}</p>
                    <p className="mt-1 text-sm text-slate-600">{row.insight}</p>
                    <p className="mt-1 text-xs text-slate-400">
                      Avg score {row.avg_performance} · {row.content_count} pieces
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function BenchmarkStat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg bg-slate-50 p-4">
      <p className="text-xs text-slate-500">{label}</p>
      <p className="text-lg font-semibold text-slate-900">{value}</p>
    </div>
  );
}
