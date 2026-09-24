"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { toast } from "sonner";
import { connectAgentStream } from "@/lib/agent-stream";
import { api } from "@/lib/api";
import type { AgentStreamEvent, ReviewDecision } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Brain,
  Target,
  Search,
  PenTool,
  Megaphone,
  UserCheck,
  Shield,
  CheckCircle2,
  Loader2,
  AlertCircle,
  Pause,
} from "lucide-react";

const AGENT_CONFIG = [
  { id: "orchestrate", label: "Orchestrator", icon: Brain, description: "Parsing brief & planning" },
  { id: "strategise", label: "Strategy", icon: Target, description: "Campaign strategy" },
  { id: "seo_research", label: "SEO Research", icon: Search, description: "Keywords & optimization" },
  { id: "create_content", label: "Content Writer", icon: PenTool, description: "Creating content" },
  { id: "write_ads", label: "Ad Copy", icon: Megaphone, description: "Ad variants" },
  { id: "human_review", label: "Human Review", icon: UserCheck, description: "Awaiting approval" },
  { id: "qa_check", label: "QA / Brand", icon: Shield, description: "Quality check" },
];

type AgentStatus = "pending" | "running" | "complete" | "error" | "waiting";

// How far along a status is. Merging the server's view with the live stream's
// keeps whichever is further ahead, so a slow rehydrate cannot walk a finished
// agent back to "running", and a stale row cannot undo a fresh stream event.
const STATUS_RANK: Record<AgentStatus, number> = {
  pending: 0,
  running: 1,
  waiting: 1,
  complete: 2,
  error: 2,
};

function mergeStatuses(
  live: Record<string, AgentStatus>,
  server: Record<string, string>
): Record<string, AgentStatus> {
  const merged: Record<string, AgentStatus> = { ...live };
  for (const [agent, raw] of Object.entries(server)) {
    const next = raw as AgentStatus;
    if (STATUS_RANK[next] === undefined) continue;
    const current = merged[agent];
    if (!current || STATUS_RANK[next] > STATUS_RANK[current]) merged[agent] = next;
  }
  return merged;
}

interface LiveAgentDashboardProps {
  campaignId: string;
  onComplete?: () => void;
  onWaitingHuman?: () => void;
}

export function LiveAgentDashboard({ campaignId, onComplete, onWaitingHuman }: LiveAgentDashboardProps) {
  const { getToken } = useAuth();

  const [agentStatuses, setAgentStatuses] = useState<Record<string, AgentStatus>>({});
  // Value intentionally unread: only the setter is used, to keep the stream handler's
  // "current agent" write path intact for future UI without an unused-variable warning.
  const [, setCurrentAgent] = useState<string>("");
  const [progress, setProgress] = useState(0);
  const [events, setEvents] = useState<AgentStreamEvent[]>([]);
  const [isComplete, setIsComplete] = useState(false);
  const [reviewSubmitting, setReviewSubmitting] = useState<ReviewDecision | null>(null);
  const disconnectRef = useRef<(() => void) | null>(null);

  /**
   * Resume the paused graph with a review decision.
   *
   * The graph compiles with `interrupt_before=["human_review"]`, so this PATCH is
   * the only thing that restarts a campaign — a failure here strands it in
   * `running` forever. It must therefore never fail silently: on error the gate
   * stays on screen with the backend's own message so the decision can be retried.
   */
  const submitDecision = async (decision: ReviewDecision) => {
    if (reviewSubmitting) return;
    setReviewSubmitting(decision);
    try {
      await api.submitReview(campaignId, decision);
      setAgentStatuses((prev) => ({
        ...prev,
        human_review: decision === "approved" ? "complete" : "running",
      }));
      toast.success(
        decision === "approved" ? "Approved — resuming pipeline" : "Revisions requested"
      );
    } catch (e) {
      const message = e instanceof Error ? e.message : "Could not submit review";
      toast.error(`Review not submitted: ${message}`);
    } finally {
      setReviewSubmitting(null);
    }
  };

  // Held in refs so a parent re-render (new inline callback identity) cannot tear
  // down the stream and blank the dashboard.
  const onCompleteRef = useRef(onComplete);
  const onWaitingHumanRef = useRef(onWaitingHuman);
  onCompleteRef.current = onComplete;
  onWaitingHumanRef.current = onWaitingHuman;

  /**
   * Rehydrate from the database.
   *
   * The SSE stream replays nothing: its queue is single-consumer and is dropped
   * once the run ends, so a client that was not connected for a step never learns
   * about it, and a reconnect after the run is answered with "No active pipeline".
   * Without this read the dashboard shows an untouched pipeline at 0% whenever it
   * remounts or the browser drops the connection — which is what happens on every
   * tab switch.
   */
  const syncProgress = useCallback(async () => {
    try {
      const p = await api.getCampaignProgress(campaignId);
      setAgentStatuses((prev) => mergeStatuses(prev, p.agent_statuses));
      setProgress((prev) => Math.max(prev, p.progress));
      if (p.campaign_status === "completed") setIsComplete(true);
    } catch {
      // A failed sync must leave whatever the stream has already shown intact.
    }
  }, [campaignId]);

  useEffect(() => {
    void syncProgress();
  }, [syncProgress]);

  // Coming back to the tab is exactly when the local view is most likely stale:
  // the browser may have dropped the EventSource while the tab was hidden.
  useEffect(() => {
    function onVisible() {
      if (document.visibilityState === "visible") void syncProgress();
    }
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", onVisible);
    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", onVisible);
    };
  }, [syncProgress]);

  useEffect(() => {
    let disconnectFn: (() => void) | null = null;
    let cancelled = false;

    getToken()
      .catch(() => null)
      .then((t) => {
        if (!t || cancelled) return;
        disconnectFn = connectAgentStream(
          campaignId,
          t,
          (event) => {
            setEvents((prev) => [...prev, event]);

            if (event.type === "step_complete") {
              setAgentStatuses((prev) => ({
                ...prev,
                [event.agent]: "complete",
              }));
              setProgress(event.progress);
            }

            if (event.type === "step_start") {
              setCurrentAgent(event.agent);
              setAgentStatuses((prev) => ({
                ...prev,
                [event.agent]: "running",
              }));
            }

            if (event.type === "waiting_human") {
              setAgentStatuses((prev) => ({
                ...prev,
                human_review: "waiting",
              }));
              onWaitingHumanRef.current?.();
            }

            if (event.type === "complete") {
              setIsComplete(true);
              setProgress(100);
              onCompleteRef.current?.();
            }

            if (event.type === "error" && event.agent) {
              // A stream-level error carries no agent ("No active pipeline for
              // this campaign" on a reconnect after the run ended). Marking a
              // blank agent failed would paint the pipeline red for a run that
              // actually succeeded, so only node errors are recorded here.
              setAgentStatuses((prev) => ({
                ...prev,
                [event.agent]: "error",
              }));
            }
          },
          () => {}
        );
        disconnectRef.current = disconnectFn;
        if (cancelled) {
          disconnectFn();
          disconnectRef.current = null;
        }
      });

    return () => {
      cancelled = true;
      disconnectFn?.();
      disconnectRef.current?.();
      disconnectRef.current = null;
    };
  }, [campaignId, getToken]);


  function getStatusIcon(agentId: string) {
    const status = agentStatuses[agentId];
    switch (status) {
      case "running":
        return <Loader2 className="h-4 w-4 animate-spin text-accent-text" />;
      case "complete":
        return <CheckCircle2 className="h-4 w-4 text-emerald-600" />;
      case "error":
        return <AlertCircle className="h-4 w-4 text-red-600" />;
      case "waiting":
        return <Pause className="h-4 w-4 text-amber-600" />;
      default:
        return <div className="h-3 w-3 rounded-full border border-slate-300" />;
    }
  }

  const STATUS_TEXT: Record<AgentStatus, string> = {
    pending: "queued",
    running: "running",
    complete: "done",
    error: "error",
    waiting: "waiting on you",
  };

  return (
    <div className="space-y-5">
      {/* Progress bar */}
      <div className="rounded-xl border border-line bg-panel/70 p-5 shadow-soft backdrop-blur-xl">
        <div className="flex items-end justify-between gap-4">
          <div>
            <div className="font-mono text-[11px] text-muted">Pipeline Progress</div>
            <div className="mt-1 font-display text-3xl font-semibold tabular-nums tracking-tight text-ink">
              {progress}
              <span className="text-lg text-muted">%</span>
            </div>
          </div>
          {!isComplete && progress > 0 && (
            <span className="flex items-center gap-1.5 font-mono text-[11px] text-accent-text">
              <span className="h-1.5 w-1.5 rounded-full bg-accent motion-safe:animate-pulse-dot" />
              live
            </span>
          )}
        </div>
        <div
          className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-slate-200"
          role="progressbar"
          aria-label="Pipeline progress"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={progress}
        >
          <div
            className={cn(
              "h-full rounded-full transition-all duration-700 ease-out",
              isComplete ? "bg-emerald-500" : "bg-gradient-to-r from-[#E4A72E] to-accent shadow-[0_0_10px_rgb(var(--c-accent)/0.5)]"
            )}
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      {/* Agent pipeline */}
      <ol className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {AGENT_CONFIG.map((agent, i) => {
          const status = agentStatuses[agent.id] || "pending";
          const isActive = status === "running";

          return (
            <li
              key={agent.id}
              style={{ animationDelay: `${i * 0.04}s` }}
              className={cn(
                "flex items-center gap-3 rounded-xl border p-3.5 backdrop-blur-xl transition-colors duration-300 motion-safe:animate-screen-in",
                isActive
                  ? "border-accent/60 bg-accent/10 shadow-[0_0_24px_rgb(var(--c-accent)/0.15)]"
                  : status === "complete"
                  ? "border-emerald-200 bg-emerald-50/60"
                  : status === "waiting"
                  ? "border-amber-300 bg-amber-50/70"
                  : status === "error"
                  ? "border-red-200 bg-red-50/60"
                  : "border-line bg-panel/60"
              )}
            >
              <span
                className={cn(
                  "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border",
                  isActive ? "border-accent/60 text-accent-text" : "border-line text-muted"
                )}
              >
                <agent.icon className="h-4 w-4" />
              </span>

              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[10px] text-muted">{String(i + 1).padStart(2, "0")}</span>
                  <span className="truncate text-sm font-semibold text-ink">{agent.label}</span>
                </div>
                <p className="mt-0.5 truncate text-xs text-muted">{agent.description}</p>
              </div>

              <div className="flex shrink-0 flex-col items-end gap-1">
                {getStatusIcon(agent.id)}
                <span className="font-mono text-[10px] text-muted">{STATUS_TEXT[status]}</span>
              </div>
            </li>
          );
        })}
      </ol>

      {agentStatuses["human_review"] === "waiting" && (
        <div className="rounded-xl border border-amber-300 bg-amber-50 p-5 shadow-[0_0_30px_rgb(var(--c-accent)/0.12)] motion-safe:animate-screen-in">
          <div className="mb-2 flex items-center gap-2">
            <UserCheck className="h-5 w-5 text-amber-600" />
            <h3 className="font-display font-semibold text-amber-900">Review Required</h3>
          </div>
          <p className="mb-4 text-sm text-amber-800">
            Content has been generated. Review the content tab and approve or request revisions.
          </p>
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => submitDecision("approved")} disabled={reviewSubmitting !== null}>
              {reviewSubmitting === "approved" ? "Approving…" : "Approve & Continue"}
            </Button>
            <Button
              variant="secondary"
              onClick={() => submitDecision("revise_content")}
              disabled={reviewSubmitting !== null}
              className="border-amber-300 bg-panel text-amber-800 hover:bg-amber-100 hover:text-amber-900"
            >
              {reviewSubmitting === "revise_content" ? "Requesting…" : "Request Revisions"}
            </Button>
          </div>
        </div>
      )}

      {/* Event log */}
      {events.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-line bg-panel/70 shadow-soft backdrop-blur-xl">
          <div className="flex items-center justify-between border-b border-line px-4 py-3">
            <h3 className="text-sm font-semibold text-ink">Agent Activity Log</h3>
            <span className="font-mono text-[10px] text-muted">SSE</span>
          </div>
          <div className="max-h-56 overflow-y-auto bg-canvas/40 p-4" aria-live="polite">
            <div className="space-y-2 font-mono text-[11.5px]">
              {events.filter(e => e.type !== "heartbeat").map((event, idx) => (
                <div key={idx} className="flex items-start gap-2">
                  <span className="mt-0.5 shrink-0 text-muted">
                    {new Date(event.timestamp).toLocaleTimeString()}
                  </span>
                  <span className={cn(
                    "shrink-0 rounded border px-1.5 py-0.5",
                    event.type === "error" ? "border-red-200 bg-red-50 text-red-700" :
                    event.type === "complete" ? "border-emerald-200 bg-emerald-50 text-emerald-700" :
                    "border-line bg-slate-500/5 text-accent-text"
                  )}>
                    {event.agent}
                  </span>
                  <span className="min-w-0 break-words text-ink">{event.content}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
