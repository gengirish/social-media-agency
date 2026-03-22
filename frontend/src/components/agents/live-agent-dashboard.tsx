"use client";

import { useEffect, useState, useRef } from "react";
import { connectAgentStream } from "@/lib/agent-stream";
import type { AgentStreamEvent } from "@/lib/api";
import { cn } from "@/lib/utils";
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

interface LiveAgentDashboardProps {
  campaignId: string;
  onComplete?: () => void;
  onWaitingHuman?: () => void;
}

export function LiveAgentDashboard({ campaignId, onComplete, onWaitingHuman }: LiveAgentDashboardProps) {
  const [agentStatuses, setAgentStatuses] = useState<Record<string, AgentStatus>>({});
  const [currentAgent, setCurrentAgent] = useState<string>("");
  const [progress, setProgress] = useState(0);
  const [events, setEvents] = useState<AgentStreamEvent[]>([]);
  const [isComplete, setIsComplete] = useState(false);
  const disconnectRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    const disconnect = connectAgentStream(
      campaignId,
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
          onWaitingHuman?.();
        }

        if (event.type === "complete") {
          setIsComplete(true);
          setProgress(100);
          onComplete?.();
        }

        if (event.type === "error") {
          setAgentStatuses((prev) => ({
            ...prev,
            [event.agent]: "error",
          }));
        }
      },
      () => {}
    );

    disconnectRef.current = disconnect;
    return () => disconnect();
  }, [campaignId, onComplete, onWaitingHuman]);

  function getStatusIcon(agentId: string) {
    const status = agentStatuses[agentId];
    switch (status) {
      case "running":
        return <Loader2 className="h-5 w-5 animate-spin text-indigo-600" />;
      case "complete":
        return <CheckCircle2 className="h-5 w-5 text-emerald-500" />;
      case "error":
        return <AlertCircle className="h-5 w-5 text-red-500" />;
      case "waiting":
        return <Pause className="h-5 w-5 text-amber-500" />;
      default:
        return <div className="h-5 w-5 rounded-full border-2 border-slate-200" />;
    }
  }

  return (
    <div className="space-y-6">
      {/* Progress bar */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-sm">
          <span className="font-medium text-slate-700">Pipeline Progress</span>
          <span className="text-slate-500">{progress}%</span>
        </div>
        <div className="h-2.5 w-full overflow-hidden rounded-full bg-slate-100">
          <div
            className={cn(
              "h-full rounded-full transition-all duration-700 ease-out",
              isComplete ? "bg-emerald-500" : "bg-indigo-600"
            )}
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      {/* Agent pipeline */}
      <div className="space-y-2">
        {AGENT_CONFIG.map((agent, idx) => {
          const status = agentStatuses[agent.id] || "pending";
          const isActive = status === "running";

          return (
            <div
              key={agent.id}
              className={cn(
                "flex items-center gap-4 rounded-xl border p-4 transition-all",
                isActive
                  ? "border-indigo-200 bg-indigo-50/50 shadow-sm"
                  : status === "complete"
                  ? "border-emerald-100 bg-emerald-50/30"
                  : status === "waiting"
                  ? "border-amber-200 bg-amber-50/50"
                  : status === "error"
                  ? "border-red-200 bg-red-50/30"
                  : "border-slate-100 bg-white"
              )}
            >
              {getStatusIcon(agent.id)}

              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <agent.icon className={cn(
                    "h-4 w-4",
                    isActive ? "text-indigo-600" : "text-slate-400"
                  )} />
                  <span className={cn(
                    "text-sm font-semibold",
                    isActive ? "text-indigo-900" : "text-slate-700"
                  )}>
                    {agent.label}
                  </span>
                </div>
                <p className="mt-0.5 text-xs text-slate-500">{agent.description}</p>
              </div>

              {isActive && (
                <div className="flex gap-1">
                  {[0, 1, 2].map((i) => (
                    <div
                      key={i}
                      className="h-1.5 w-1.5 rounded-full bg-indigo-600 animate-pulse-dot"
                      style={{ animationDelay: `${i * 0.3}s` }}
                    />
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Event log */}
      {events.length > 0 && (
        <div className="rounded-xl border border-slate-200 bg-white">
          <div className="border-b border-slate-100 px-4 py-3">
            <h3 className="text-sm font-semibold text-slate-700">Agent Activity Log</h3>
          </div>
          <div className="max-h-48 overflow-y-auto p-4">
            <div className="space-y-2">
              {events.filter(e => e.type !== "heartbeat").map((event, idx) => (
                <div key={idx} className="flex items-start gap-2 text-xs">
                  <span className="mt-0.5 text-slate-400">
                    {new Date(event.timestamp).toLocaleTimeString()}
                  </span>
                  <span className={cn(
                    "rounded px-1.5 py-0.5 font-mono",
                    event.type === "error" ? "bg-red-100 text-red-700" :
                    event.type === "complete" ? "bg-emerald-100 text-emerald-700" :
                    "bg-slate-100 text-slate-600"
                  )}>
                    {event.agent}
                  </span>
                  <span className="text-slate-600">{event.content}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
