"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, campaignFailureSummary, type Campaign, type Client } from "@/lib/api";
import { platformLabel } from "@/lib/platforms";
import { clientLabel, useActiveClient } from "@/lib/active-client";
import { useClientScope, type ClientScope } from "@/lib/client-scope";
import { useSession } from "@/lib/session";
import { toast } from "sonner";
import { Plus, Megaphone, ArrowUpRight, AlertTriangle } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/panel";
import { EmptyState, LoadingState } from "@/components/ui/empty-state";
import { SegmentedTabs, Tag } from "@/components/ui/tabs";
import { CampaignStatusBadge } from "@/components/ui/campaign-status";

export default function CampaignsPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [clients, setClients] = useState<Client[]>([]);
  const [loading, setLoading] = useState(true);
  // CF-10: this listed every client's campaigns whatever the top-nav switcher
  // said, which is the one screen in Create that ignored it. Same scope store
  // as the Queue and Calendar, so the choice carries across.
  const { active, activeId, loading: clientsLoading } = useActiveClient();
  const { isPersonal } = useSession();
  const [scope, setScope] = useClientScope();
  // A personal account has exactly one client: no "all" to scope to.
  const clientId = scope === "client" || isPersonal ? activeId : null;

  useEffect(() => {
    // Wait for the switcher — firing with a null id would fetch every client's
    // campaigns and then replace them a moment later.
    if (clientsLoading) return;
    if (scope === "client" && !isPersonal && !activeId) {
      setCampaigns([]);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    Promise.all([api.getCampaigns(clientId ?? undefined), api.getClientsForLookup()])
      .then(([c, cl]) => {
        if (cancelled) return;
        setCampaigns(c.items);
        setClients(cl);
      })
      .catch((err) => !cancelled && toast.error(err.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [clientId, scope, activeId, isPersonal, clientsLoading]);

  if (loading) {
    return <LoadingState label="Loading campaigns" />;
  }

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Create"
        title="Campaigns"
        description="Launch AI-powered marketing campaigns"
        actions={
          <>
            {!isPersonal && (
              <SegmentedTabs
                label="Campaign scope"
                items={[
                  { id: "client" as ClientScope, label: clientLabel(active) },
                  { id: "all" as ClientScope, label: "All clients" },
                ]}
                value={scope}
                onChange={setScope}
              />
            )}
            <Link href="/campaigns/new" className={buttonVariants()}>
              <Plus className="h-4 w-4" />
              New Campaign
            </Link>
          </>
        }
      />

      {campaigns.length === 0 ? (
        <EmptyState
          icon={Megaphone}
          title="No campaigns yet"
          description="Create your first AI-powered campaign"
          action={
            <Link href="/campaigns/new" className={buttonVariants()}>
              Create Campaign
            </Link>
          }
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {campaigns.map((campaign, i) => {
            const client = clients.find((c) => c.id === campaign.client_id);
            return (
              <Link
                key={campaign.id}
                href={`/campaigns/${campaign.id}`}
                style={{ animationDelay: `${Math.min(i, 8) * 0.05}s` }}
                className="group flex flex-col rounded-xl border border-line bg-panel/70 p-5 shadow-soft backdrop-blur-xl transition-[transform,border-color,box-shadow] duration-200 hover:-translate-y-0.5 hover:border-accent/50 hover:shadow-[0_12px_32px_rgb(var(--c-accent)/0.12)] motion-safe:animate-screen-in"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-mono text-[11px] text-muted">
                      {client?.brand_name || "Unknown Client"}
                    </p>
                    <h3 className="mt-1 font-display text-base font-semibold leading-snug text-ink transition-colors group-hover:text-accent-text">
                      {campaign.name}
                    </h3>
                  </div>
                  <CampaignStatusBadge status={campaign.status} />
                </div>

                <p className="mt-3 line-clamp-2 flex-1 text-sm text-muted">{campaign.objective}</p>

                {/* CF-07: a short reason on the card, so a list of failures is
                    something to act on rather than four identical red badges. */}
                {campaignFailureSummary(campaign) && (
                  <p className="mt-2 line-clamp-2 flex items-start gap-1.5 text-xs text-red-700">
                    <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
                    {campaignFailureSummary(campaign)}
                  </p>
                )}

                <div className="mt-4 flex items-center justify-between gap-3 border-t border-line pt-3">
                  <div className="flex flex-wrap gap-1.5">
                    {campaign.channels.map((ch) => (
                      <Tag key={ch}>{platformLabel(ch)}</Tag>
                    ))}
                  </div>
                  <ArrowUpRight className="h-4 w-4 shrink-0 text-muted transition-[color,transform] group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-accent-text" />
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
