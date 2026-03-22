"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type Campaign, type Client } from "@/lib/api";
import { toast } from "sonner";
import { Plus, Megaphone, Loader2, ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";

const STATUS_COLORS: Record<string, string> = {
  planning: "bg-slate-100 text-slate-700",
  running: "bg-indigo-100 text-indigo-700",
  completed: "bg-emerald-100 text-emerald-700",
  paused: "bg-amber-100 text-amber-700",
  failed: "bg-red-100 text-red-700",
};

export default function CampaignsPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [clients, setClients] = useState<Client[]>([]);
  const [loading, setLoading] = useState(true);
  const [showWizard, setShowWizard] = useState(false);

  useEffect(() => {
    Promise.all([api.getCampaigns(), api.getClients()])
      .then(([c, cl]) => {
        setCampaigns(c.items);
        setClients(cl.items);
      })
      .catch((err) => toast.error(err.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Campaigns</h1>
          <p className="mt-1 text-slate-500">Launch AI-powered marketing campaigns</p>
        </div>
        <Link
          href="/campaigns/new"
          className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-indigo-500"
        >
          <Plus className="h-4 w-4" />
          New Campaign
        </Link>
      </div>

      {campaigns.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-200 py-16">
          <Megaphone className="mb-4 h-12 w-12 text-slate-300" />
          <h3 className="text-lg font-semibold text-slate-900">No campaigns yet</h3>
          <p className="mt-1 text-slate-500">Create your first AI-powered campaign</p>
          <Link
            href="/campaigns/new"
            className="mt-4 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-500"
          >
            Create Campaign
          </Link>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {campaigns.map((campaign) => {
            const client = clients.find((c) => c.id === campaign.client_id);
            return (
              <Link
                key={campaign.id}
                href={`/campaigns/${campaign.id}`}
                className="group rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition-all hover:border-indigo-200 hover:shadow-md"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <h3 className="font-semibold text-slate-900 group-hover:text-indigo-600">
                      {campaign.name}
                    </h3>
                    <p className="mt-1 text-sm text-slate-500">
                      {client?.brand_name || "Unknown Client"}
                    </p>
                  </div>
                  <span className={cn("rounded-full px-2.5 py-1 text-xs font-medium", STATUS_COLORS[campaign.status] || STATUS_COLORS.planning)}>
                    {campaign.status}
                  </span>
                </div>

                <p className="mt-3 line-clamp-2 text-sm text-slate-600">{campaign.objective}</p>

                <div className="mt-4 flex items-center justify-between">
                  <div className="flex gap-1.5">
                    {campaign.channels.map((ch) => (
                      <span key={ch} className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
                        {ch}
                      </span>
                    ))}
                  </div>
                  <ArrowRight className="h-4 w-4 text-slate-400 group-hover:text-indigo-600" />
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
