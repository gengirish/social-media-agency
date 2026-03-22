"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, type Campaign, type ContentPiece } from "@/lib/api";
import { LiveAgentDashboard } from "@/components/agents/live-agent-dashboard";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { Loader2, FileText, CheckCircle2, Edit3 } from "lucide-react";

const PLATFORM_COLORS: Record<string, string> = {
  linkedin: "bg-indigo-50 text-indigo-700 border-indigo-200",
  twitter: "bg-sky-50 text-sky-700 border-sky-200",
  instagram: "bg-pink-50 text-pink-700 border-pink-200",
  facebook: "bg-blue-50 text-blue-700 border-blue-200",
  tiktok: "bg-slate-50 text-slate-700 border-slate-200",
  google: "bg-red-50 text-red-700 border-red-200",
  meta: "bg-blue-50 text-blue-700 border-blue-200",
};

export default function CampaignDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [content, setContent] = useState<ContentPiece[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<"agents" | "content">("agents");

  useEffect(() => {
    if (!id) return;
    api.getCampaign(id)
      .then(setCampaign)
      .catch((err) => toast.error(err.message))
      .finally(() => setLoading(false));
  }, [id]);

  function loadContent() {
    if (!id) return;
    api.getCampaignContent(id)
      .then((res) => setContent(res.items))
      .catch(() => {});
  }

  function handlePipelineComplete() {
    loadContent();
    toast.success("Campaign pipeline completed!");
  }

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
      </div>
    );
  }

  if (!campaign) {
    return <div className="text-center text-slate-500">Campaign not found</div>;
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">{campaign.name}</h1>
          <p className="mt-1 text-slate-500">{campaign.objective}</p>
          <div className="mt-2 flex gap-2">
            {campaign.channels.map((ch) => (
              <span
                key={ch}
                className={cn("rounded-full border px-2.5 py-0.5 text-xs font-medium", PLATFORM_COLORS[ch] || "bg-slate-100 text-slate-600")}
              >
                {ch}
              </span>
            ))}
          </div>
        </div>
        <span className={cn(
          "rounded-full px-3 py-1 text-sm font-medium",
          campaign.status === "running" ? "bg-indigo-100 text-indigo-700" :
          campaign.status === "completed" ? "bg-emerald-100 text-emerald-700" :
          "bg-slate-100 text-slate-700"
        )}>
          {campaign.status}
        </span>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 rounded-lg bg-slate-100 p-1">
        <button
          onClick={() => setActiveTab("agents")}
          className={cn(
            "flex-1 rounded-md px-4 py-2 text-sm font-medium transition-colors",
            activeTab === "agents" ? "bg-white text-slate-900 shadow-sm" : "text-slate-600 hover:text-slate-900"
          )}
        >
          Live Agents
        </button>
        <button
          onClick={() => { setActiveTab("content"); loadContent(); }}
          className={cn(
            "flex-1 rounded-md px-4 py-2 text-sm font-medium transition-colors",
            activeTab === "content" ? "bg-white text-slate-900 shadow-sm" : "text-slate-600 hover:text-slate-900"
          )}
        >
          Content ({content.length})
        </button>
      </div>

      {/* Agent Dashboard */}
      {activeTab === "agents" && (
        <LiveAgentDashboard
          campaignId={id}
          onComplete={handlePipelineComplete}
        />
      )}

      {/* Content Library */}
      {activeTab === "content" && (
        <div className="space-y-4">
          {content.length === 0 ? (
            <div className="flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-200 py-12">
              <FileText className="mb-3 h-10 w-10 text-slate-300" />
              <p className="text-sm text-slate-500">Content will appear here after agents finish</p>
            </div>
          ) : (
            content.map((piece) => (
              <div key={piece.id} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-2">
                    <span className={cn("rounded-full border px-2.5 py-0.5 text-xs font-medium", PLATFORM_COLORS[piece.platform] || "bg-slate-100")}>
                      {piece.platform}
                    </span>
                    <span className="text-xs text-slate-400">{piece.content_type}</span>
                  </div>
                  <div className="flex gap-2">
                    {piece.status === "draft" && (
                      <button
                        onClick={async () => {
                          await api.approveContent(piece.id);
                          loadContent();
                          toast.success("Content approved!");
                        }}
                        className="flex items-center gap-1 rounded-lg bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-700 hover:bg-emerald-100"
                      >
                        <CheckCircle2 className="h-3.5 w-3.5" /> Approve
                      </button>
                    )}
                  </div>
                </div>
                {piece.title && (
                  <h3 className="mt-3 font-semibold text-slate-900">{piece.title}</h3>
                )}
                <p className="mt-2 whitespace-pre-wrap text-sm text-slate-700">{piece.body}</p>
                {piece.hashtags && piece.hashtags.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-1">
                    {piece.hashtags.map((tag: string, i: number) => (
                      <span key={i} className="text-xs text-indigo-600">#{tag}</span>
                    ))}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
