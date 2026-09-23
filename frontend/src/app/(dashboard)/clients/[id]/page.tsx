"use client";

import { useActiveClient } from "@/lib/active-client";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";
import Link from "next/link";
import { Archive, ArchiveRestore, Globe, Mail, Pencil } from "lucide-react";
import { api, apiErrorCode, ApiError, type Client, type SavedBrandProfile } from "@/lib/api";
import { trackFeature } from "@/lib/analytics";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/panel";
import { SectionCard } from "@/components/ui/section-card";
import { StatCard } from "@/components/ui/stat-card";
import { EmptyState, LoadingState } from "@/components/ui/empty-state";
import { EditClientForm } from "@/components/clients/edit-client-form";

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
  const { refresh: refreshActiveClient } = useActiveClient();
  const params = useParams();
  const clientId = params.id as string;
  const [data, setData] = useState<ClientIntelligence | null>(null);
  const [client, setClient] = useState<Client | null>(null);
  const [profile, setProfile] = useState<SavedBrandProfile | null>(null);
  const [editing, setEditing] = useState(false);
  const [archiving, setArchiving] = useState(false);
  const router = useRouter();
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const [json, clientRow, brandProfile] = await Promise.all([
          api.getClientIntelligence(clientId) as unknown as Promise<ClientIntelligence>,
          api.getClient(clientId),
          // A client without a brand profile is normal — the API answers 404.
          api.getBrandProfile(clientId).catch(() => null),
        ]);
        if (!cancelled) {
          setData(json);
          setClient(clientRow);
          setProfile(brandProfile);
        }
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

  async function handleArchive() {
    if (!client) return;
    const ok = window.confirm(
      `Archive ${client.brand_name}? It will be hidden from client lists and nothing new can be scheduled or published for it. Campaigns and posts are kept, and you can restore it any time.`
    );
    if (!ok) return;
    setArchiving(true);
    try {
      let unscheduled = 0;
      try {
        await api.archiveClient(client.id);
        void refreshActiveClient();
      } catch (err) {
        if (apiErrorCode(err) !== "has_scheduled_posts") throw err;
        const count = ((err as ApiError).detail as { count?: number }).count ?? 0;
        const posts = `${count} scheduled post${count === 1 ? "" : "s"}`;
        if (
          !window.confirm(
            `${client.brand_name} has ${posts}. Archiving will unschedule ${count === 1 ? "it" : "them"} — ${count === 1 ? "it stays" : "they stay"} approved in the Queue and can be rescheduled after a restore. Archive anyway?`
          )
        ) {
          setArchiving(false);
          return;
        }
        await api.archiveClient(client.id, true);
        void refreshActiveClient();
        unscheduled = count;
      }
      trackFeature("client-archive", { unscheduled });
      toast.success(
        unscheduled
          ? `${client.brand_name} archived, ${unscheduled} post${unscheduled === 1 ? "" : "s"} unscheduled`
          : `${client.brand_name} archived`
      );
      router.push("/clients");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not archive client");
      setArchiving(false);
    }
  }

  async function handleRestore() {
    if (!client) return;
    setArchiving(true);
    try {
      setClient(await api.restoreClient(client.id));
      void refreshActiveClient();
      trackFeature("client-restore");
      toast.success(`${client.brand_name} restored`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not restore client");
    } finally {
      setArchiving(false);
    }
  }

  if (loading) {
    return <LoadingState label="Loading client" />;
  }

  if (!data || !client) {
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
        <PageHeader
          eyebrow="Client"
          title={client.brand_name}
          description={client.industry || "No industry set"}
          actions={
            !editing && (
              <div className="flex flex-wrap gap-2">
                <Button variant="secondary" onClick={() => setEditing(true)}>
                  <Pencil className="h-4 w-4" /> Edit client
                </Button>
                {client.is_active && (
                  <Button variant="ghost" onClick={handleArchive} disabled={archiving}>
                    <Archive className="h-4 w-4" /> {archiving ? "Archiving..." : "Archive"}
                  </Button>
                )}
              </div>
            )
          }
        />
      </div>

      {!client.is_active && (
        <div
          role="status"
          className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-accent/40 bg-accent/5 px-4 py-3 text-sm"
        >
          <p className="text-ink">
            This client is archived. It is hidden from client lists, and nothing can be scheduled or published for it.
          </p>
          <Button size="sm" onClick={handleRestore} disabled={archiving}>
            <ArchiveRestore className="h-4 w-4" /> {archiving ? "Restoring..." : "Restore"}
          </Button>
        </div>
      )}

      {editing ? (
        <EditClientForm
          client={client}
          profile={profile}
          onCancel={() => setEditing(false)}
          onSaved={(updated, savedProfile) => {
            setClient(updated);
            setProfile(savedProfile);
            setData((d) =>
              d && {
                ...d,
                client_name: updated.brand_name,
                industry: updated.industry,
                brand_voice: savedProfile
                  ? {
                      voice_description: savedProfile.voice_description ?? "",
                      tone_attributes: savedProfile.tone_attributes ?? {},
                      target_audience: savedProfile.target_audience ?? "",
                    }
                  : d.brand_voice,
              }
            );
            setEditing(false);
          }}
        />
      ) : (
        (client.description || client.website_url || client.contact_email) && (
          <SectionCard eyebrow="Profile" title="About" bodyClassName="space-y-3">
            {client.description && <p className="text-sm leading-relaxed text-ink">{client.description}</p>}
            {(client.website_url || client.contact_email) && (
              <div className="flex flex-wrap items-center gap-x-6 gap-y-2 font-mono text-xs text-muted">
                {client.website_url && (
                  <a
                    href={/^https?:\/\//i.test(client.website_url) ? client.website_url : `https://${client.website_url}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1.5 transition-colors hover:text-accent-text"
                  >
                    <Globe className="h-3.5 w-3.5" /> {client.website_url}
                  </a>
                )}
                {client.contact_email && (
                  <a
                    href={`mailto:${client.contact_email}`}
                    className="flex items-center gap-1.5 transition-colors hover:text-accent-text"
                  >
                    <Mail className="h-3.5 w-3.5" /> {client.contact_email}
                  </a>
                )}
              </div>
            )}
          </SectionCard>
        )
      )}

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
