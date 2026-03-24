"use client";

import { useEffect, useState } from "react";
import { api, type DashboardStats } from "@/lib/api";
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

export default function AnalyticsPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .getStats()
      .then(setStats)
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : "Failed to load stats")
      )
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-center text-red-700">
        Failed to load analytics: {error}
      </div>
    );
  }

  if (!stats) return null;

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

  /** API exposes draft count; other rows are non-draft (approved, scheduled, published, etc.). */
  const nonDraft = Math.max(0, stats.total_content_pieces - stats.content_drafts);
  const contentBreakdown = [
    { label: "Draft", value: stats.content_drafts, color: "bg-amber-500" },
    { label: "Approved / scheduled / published", value: nonDraft, color: "bg-emerald-500" },
  ];
  const totalContent = stats.total_content_pieces || 1;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Analytics</h1>
        <p className="mt-1 text-slate-500">Campaign performance and platform insights</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {kpis.map((kpi) => (
          <div key={kpi.label} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
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
            Share of campaigns currently running vs the rest of your portfolio (from live stats, not a dated
            timeline).
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
          Connect social platform accounts in Settings to see per-platform engagement metrics, optimal posting
          times, and content performance analytics.
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
    </div>
  );
}
