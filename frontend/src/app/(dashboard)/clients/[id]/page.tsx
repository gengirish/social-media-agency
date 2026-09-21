"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { PageHeader } from "@/components/ui/panel";
import { SectionCard } from "@/components/ui/section-card";
import { StatCard } from "@/components/ui/stat-card";
import { EmptyState, LoadingState } from "@/components/ui/empty-state";

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
    return <LoadingState label="Loading client" />;
  }

  if (!data) {
    return (
      <EmptyState
        title="Client not found or you don't have access."
        action={
          <Link href="/clients" className="font-mono text-xs text-accent-text hover:underline">
            Back to clients
          </Link>
        }
      />
    );
  }

  const statusBreakdown = data.status_breakdown || {};
  const platformBreakdown = data.platform_breakdown || {};
  const totalContent = Object.values(statusBreakdown).reduce((a, b) => a + b, 0);
  const maxPlatform = Math.max(1, ...Object.values(platformBreakdown));

  return (
    <div className="space-y-8">
      <div className="space-y-3">
        <Link
          href="/clients"
          className="inline-flex items-center gap-1 font-mono text-[11px] text-muted transition-colors hover:text-ink"
        >
          ← All clients
        </Link>
        <PageHeader eyebrow="Client" title={data.client_name} description={data.industry || "No industry set"} />
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="Campaigns" value={data.campaign_count} />
        <StatCard label="Total Content" value={totalContent} delay={0.05} />
        <StatCard label="Published" value={statusBreakdown.published ?? 0} tone="success" delay={0.1} />
        <StatCard label="Platforms" value={Object.keys(platformBreakdown).length} delay={0.15} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <SectionCard eyebrow="Distribution" title="Platform breakdown" delay={0.1}>
          {Object.keys(platformBreakdown).length === 0 ? (
            <p className="text-sm text-muted">No content by platform yet.</p>
          ) : (
            <ul className="space-y-3">
              {Object.entries(platformBreakdown).map(([platform, count]) => (
                <li key={platform}>
                  <div className="mb-1 flex items-center justify-between text-sm">
                    <span className="capitalize text-ink">{platform}</span>
                    <span className="font-mono text-xs text-muted">{count}</span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-slate-200">
                    <div
                      className="h-full rounded-full bg-accent"
                      style={{ width: `${Math.round((count / maxPlatform) * 100)}%` }}
                    />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>

        <SectionCard eyebrow="Voice" title="Brand voice" delay={0.15} bodyClassName="space-y-3">
          <p className="text-sm leading-relaxed text-ink">
            {data.brand_voice?.voice_description || "Not configured"}
          </p>
          <p className="border-l-2 border-accent/60 pl-3 text-sm text-muted">
            <strong className="font-medium text-ink">Target:</strong>{" "}
            {data.brand_voice?.target_audience || "N/A"}
          </p>
        </SectionCard>
      </div>

      {(data.top_content || []).length > 0 && (
        <SectionCard eyebrow="Performance" title="Top performing content" delay={0.2}>
          <ul className="divide-y divide-line">
            {data.top_content.map((c) => (
              <li key={c.id} className="flex items-center justify-between gap-4 py-3 first:pt-0 last:pb-0">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-ink">{c.title || "Untitled"}</p>
                  <p className="font-mono text-[11px] capitalize text-muted">{c.platform}</p>
                </div>
                <span className="font-display text-lg font-semibold tabular-nums text-accent-text">
                  {c.performance_score != null ? c.performance_score.toFixed(1) : "N/A"}
                </span>
              </li>
            ))}
          </ul>
        </SectionCard>
      )}
    </div>
  );
}
