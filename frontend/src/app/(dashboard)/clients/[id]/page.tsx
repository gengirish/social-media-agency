"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";

interface TopContentRow {
  id: string;
  platform: string;
  title: string;
  performance_score: number | null;
}

interface BrandVoice {
  voice_description: string;
  tone_attributes: Record<string, unknown>;
  target_audience: string;
}

interface ClientIntelligence {
  client_name: string;
  industry: string | null;
  campaign_count: number;
  platform_breakdown: Record<string, number>;
  status_breakdown: Record<string, number>;
  top_content: TopContentRow[];
  brand_voice: BrandVoice;
}

export default function ClientDetailPage() {
  const params = useParams();
  const clientId = params.id as string;
  const [data, setData] = useState<ClientIntelligence | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const json = (await api.getClientIntelligence(clientId)) as unknown as ClientIntelligence;
        if (!cancelled) setData(json);
      } catch {
        if (!cancelled) setData(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [clientId]);

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="space-y-4 py-12 text-center">
        <p className="text-slate-500">Client not found or you don&apos;t have access.</p>
        <Link href="/clients" className="text-sm font-medium text-indigo-600 hover:text-indigo-500">
          Back to clients
        </Link>
      </div>
    );
  }

  const statusBreakdown = data.status_breakdown || {};
  const platformBreakdown = data.platform_breakdown || {};
  const totalContent = Object.values(statusBreakdown).reduce((a, b) => a + b, 0);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">{data.client_name}</h1>
          <p className="text-sm text-slate-500">{data.industry || "No industry set"}</p>
        </div>
        <Link
          href="/clients"
          className="text-sm font-medium text-indigo-600 hover:text-indigo-500"
        >
          ← All clients
        </Link>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Campaigns" value={data.campaign_count} />
        <Stat label="Total Content" value={totalContent} />
        <Stat label="Published" value={statusBreakdown.published ?? 0} />
        <Stat label="Platforms" value={Object.keys(platformBreakdown).length} />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-900">Platform breakdown</h2>
          <div className="mt-4 space-y-2">
            {Object.keys(platformBreakdown).length === 0 ? (
              <p className="text-sm text-slate-500">No content by platform yet.</p>
            ) : (
              Object.entries(platformBreakdown).map(([platform, count]) => (
                <div key={platform} className="flex items-center justify-between">
                  <span className="text-sm capitalize text-slate-600">{platform}</span>
                  <span className="text-sm font-medium text-slate-900">{count}</span>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-900">Brand voice</h2>
          <p className="mt-2 text-sm text-slate-600">
            {data.brand_voice?.voice_description || "Not configured"}
          </p>
          <p className="mt-2 text-sm text-slate-600">
            <strong className="text-slate-800">Target:</strong>{" "}
            {data.brand_voice?.target_audience || "N/A"}
          </p>
        </div>
      </div>

      {(data.top_content || []).length > 0 && (
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-900">Top performing content</h2>
          <div className="mt-4 space-y-3">
            {data.top_content.map((c) => (
              <div
                key={c.id}
                className="flex items-center justify-between border-b border-slate-100 pb-3 last:border-0 last:pb-0"
              >
                <div>
                  <p className="text-sm font-medium text-slate-900">{c.title || "Untitled"}</p>
                  <p className="text-xs capitalize text-slate-500">{c.platform}</p>
                </div>
                <span className="text-sm font-medium text-indigo-600">
                  {c.performance_score != null ? c.performance_score.toFixed(1) : "N/A"}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-sm text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-bold text-slate-900">{value}</p>
    </div>
  );
}
