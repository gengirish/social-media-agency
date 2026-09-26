"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  adVariantOf,
  api,
  apiErrorCode,
  campaignFailureSummary,
  moderationIssues,
  unusableReason,
  type Campaign,
  type ContentPiece,
} from "@/lib/api";
import { platformLabel } from "@/lib/platforms";
import { AdVariantCard } from "@/components/content/ad-variant-card";
import { LiveAgentDashboard } from "@/components/agents/live-agent-dashboard";
import { toast } from "sonner";
import { FileText, CheckCircle2, Bot, ArrowLeft, RotateCcw, AlertTriangle } from "lucide-react";
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

  const loadContent = useCallback(() => {
    if (!id) return;
    api.getCampaignContent(id)
      .then((res) => setContent(res.items))
      .catch(() => {});
  }, [id]);

  // Load on mount, not only when the Content tab is opened: the "complete" SSE
  // event that used to be the trigger is delivered once, to whoever happens to be
  // connected, so a campaign that finished while the tab was in the background
  // would otherwise show an empty library until reloaded.
  useEffect(() => {
    loadContent();
  }, [loadContent]);

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

  const failureSummary = campaignFailureSummary(campaign);

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
                <Tag key={ch}>{platformLabel(ch)}</Tag>
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

      {/* CF-07: a failed campaign used to show only a red badge, so there was
          nothing to act on and no way to tell a bad key from a bad prompt. */}
      {failureSummary && (
        <div className="flex items-start gap-2.5 rounded-xl border border-red-200 bg-red-50 p-4">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-600" aria-hidden />
          <div className="min-w-0 space-y-1">
            <p className="text-sm font-medium text-red-800">This campaign failed</p>
            <p className="break-words text-sm text-red-700">{failureSummary}</p>
            <p className="text-xs text-red-700/80">
              Re-run it once the cause is fixed — anything the pipeline already saved is on the
              Content tab.
            </p>
          </div>
        </div>
      )}

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

      {/* Agent Dashboard — hidden rather than unmounted, so switching to Content
          and back does not discard the run's progress and drop its stream. */}
      <div hidden={activeTab !== "agents"}>
        <LiveAgentDashboard
          key={runKey}
          campaignId={id}
          onComplete={handlePipelineComplete}
        />
      </div>

      {/* Content Library */}
      {activeTab === "content" && (
        <div className="space-y-3">
          {content.length === 0 ? (
            <EmptyState icon={FileText} title="No content yet" description="Content will appear here after agents finish" />
          ) : (
            content.map((piece, i) => {
              const ad = adVariantOf(piece);
              // CF-05: an item with nothing in it must not be approvable. The
              // pipeline now stores an empty ad variant as failed, but rows
              // created before that are drafts holding "[]", so the check is on
              // the content itself, not only the status.
              const unusable = unusableReason(piece);
              return (
              <article
                key={piece.id}
                style={{ animationDelay: `${Math.min(i, 8) * 0.04}s` }}
                className="rounded-xl border border-line bg-panel/70 p-5 shadow-soft backdrop-blur-xl motion-safe:animate-screen-in"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Tag className="text-ink">{platformLabel(piece.platform)}</Tag>
                    <span className="font-mono text-[11px] text-muted">{piece.content_type}</span>
                    <StatusBadge status={piece.status} />
                  </div>
                  <div className="flex gap-2">
                    {piece.status === "draft" && unusable === null && (
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
                {/* An ad renders in its network's own fields; only a social post
                    is a single body paragraph. */}
                <div className="mt-2">
                  {ad ? (
                    <AdVariantCard ad={ad} />
                  ) : (
                    <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink/90">{piece.body}</p>
                  )}
                </div>
                {!ad && unusable !== null && (
                  <p className="mt-2 text-xs text-muted">{unusable}</p>
                )}
                {piece.hashtags && piece.hashtags.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-x-2 gap-y-1">
                    {piece.hashtags.map((tag: string, i: number) => (
                      <span key={i} className="font-mono text-xs text-accent-text">#{tag}</span>
                    ))}
                  </div>
                )}
              </article>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}
