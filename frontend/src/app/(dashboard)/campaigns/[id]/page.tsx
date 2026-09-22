"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { api, apiErrorCode, moderationIssues, type Campaign, type ContentPiece } from "@/lib/api";
import { LiveAgentDashboard } from "@/components/agents/live-agent-dashboard";
import { toast } from "sonner";
import { FileText, CheckCircle2, Bot, ArrowLeft, RotateCcw } from "lucide-react";
import { trackFeature } from "@/lib/analytics";
import { Button } from "@/components/ui/button";
import { Eyebrow } from "@/components/ui/panel";
import { StatusBadge } from "@/components/ui/status-badge";
import { CampaignStatusBadge } from "@/components/ui/campaign-status";
import { EmptyState, LoadingState } from "@/components/ui/empty-state";
import { SegmentedTabs, Tag } from "@/components/ui/tabs";

export default function CampaignDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [content, setContent] = useState<ContentPiece[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<"agents" | "content">("agents");
  const [rerunning, setRerunning] = useState(false);
  // Bumped on re-run so the dashboard remounts and opens the new run's stream.
  const [runKey, setRunKey] = useState(0);

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

  async function handleRerun() {
    if (rerunning || !id) return;
    const ok = window.confirm(
      "Re-run the agent pipeline from the start? Any pending review is discarded. " +
        "Existing content stays; the new run adds fresh drafts for review."
    );
    if (!ok) return;
    setRerunning(true);
    try {
      const updated = await api.rerunCampaign(id);
      setCampaign(updated);
      setActiveTab("agents");
      setRunKey((k) => k + 1);
      trackFeature("campaign-rerun");
      toast.success("Pipeline restarted");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not re-run campaign");
    } finally {
      setRerunning(false);
    }
  }

  function handlePipelineComplete() {
    loadContent();
    toast.success("Campaign pipeline completed!");
  }

  if (loading) {
    return <LoadingState label="Loading campaign" />;
  }

  if (!campaign) {
    return (
      <EmptyState
        title="Campaign not found"
        action={
          <Link href="/campaigns" className="font-mono text-xs text-accent-text hover:underline">
            ← All campaigns
          </Link>
        }
      />
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="space-y-3">
        <Link
          href="/campaigns"
          className="inline-flex items-center gap-1 font-mono text-[11px] text-muted transition-colors hover:text-ink"
        >
          <ArrowLeft className="h-3 w-3" /> Campaigns
        </Link>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0 space-y-2">
            <Eyebrow>Campaign</Eyebrow>
            <h1 className="font-display text-2xl font-semibold tracking-tight text-ink sm:text-3xl">{campaign.name}</h1>
            <p className="max-w-3xl text-sm text-muted">{campaign.objective}</p>
            <div className="flex flex-wrap gap-1.5 pt-1">
              {campaign.channels.map((ch) => (
                <Tag key={ch}>{ch}</Tag>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <CampaignStatusBadge status={campaign.status} className="px-2.5 py-1 text-xs" />
            {campaign.status !== "autonomous" && (
              <Button size="sm" variant="secondary" onClick={handleRerun} disabled={rerunning}>
                <RotateCcw className="h-3.5 w-3.5" /> {rerunning ? "Restarting…" : "Re-run"}
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* Tabs */}
      <SegmentedTabs
        label="Campaign views"
        value={activeTab}
        onChange={(tab) => {
          setActiveTab(tab);
          if (tab === "content") loadContent();
        }}
        items={[
          { id: "agents", label: "Live Agents", icon: Bot },
          { id: "content", label: `Content (${content.length})`, icon: FileText },
        ]}
      />

      {/* Agent Dashboard */}
      {activeTab === "agents" && (
        <LiveAgentDashboard
          key={runKey}
          campaignId={id}
          onComplete={handlePipelineComplete}
        />
      )}

      {/* Content Library */}
      {activeTab === "content" && (
        <div className="space-y-3">
          {content.length === 0 ? (
            <EmptyState icon={FileText} title="No content yet" description="Content will appear here after agents finish" />
          ) : (
            content.map((piece, i) => (
              <article
                key={piece.id}
                style={{ animationDelay: `${Math.min(i, 8) * 0.04}s` }}
                className="rounded-xl border border-line bg-panel/70 p-5 shadow-soft backdrop-blur-xl motion-safe:animate-screen-in"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Tag className="text-ink">{piece.platform}</Tag>
                    <span className="font-mono text-[11px] text-muted">{piece.content_type}</span>
                    <StatusBadge status={piece.status} />
                  </div>
                  <div className="flex gap-2">
                    {piece.status === "draft" && (
                      <Button
                        size="sm"
                        onClick={async () => {
                          try {
                            await api.approveContent(piece.id);
                            toast.success("Content approved!");
                          } catch (err) {
                            // Moderation runs on approve. The full review, with
                            // "Approve anyway", lives in the Queue — send them there.
                            const code = apiErrorCode(err);
                            if (code === "moderation_flagged") {
                              const [first] = moderationIssues(err);
                              toast.warning("Moderation flagged this post", {
                                description: first?.message,
                                action: { label: "Review in Queue", onClick: () => router.push("/content") },
                              });
                            } else {
                              toast.error(err instanceof Error ? err.message : "Could not approve");
                            }
                          } finally {
                            loadContent();
                          }
                        }}
                      >
                        <CheckCircle2 className="h-3.5 w-3.5" /> Approve
                      </Button>
                    )}
                  </div>
                </div>
                {piece.title && (
                  <h3 className="mt-3 font-display text-base font-semibold text-ink">{piece.title}</h3>
                )}
                <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-ink/90">{piece.body}</p>
                {piece.hashtags && piece.hashtags.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-x-2 gap-y-1">
                    {piece.hashtags.map((tag: string, i: number) => (
                      <span key={i} className="font-mono text-xs text-accent-text">#{tag}</span>
                    ))}
                  </div>
                )}
              </article>
            ))
          )}
        </div>
      )}
    </div>
  );
}
