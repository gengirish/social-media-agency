"use client";

import { useEffect, useState } from "react";
import { api, type DashboardStats } from "@/lib/api";
import { Users, Megaphone, FileText, Zap, Loader2, TrendingUp } from "lucide-react";

export default function DashboardContent() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getStats()
      .then(setStats)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
      </div>
    );
  }

  const cards = [
    { label: "Clients", value: stats?.total_clients ?? 0, icon: Users, color: "text-blue-600", bg: "bg-blue-50" },
    { label: "Campaigns", value: stats?.total_campaigns ?? 0, icon: Megaphone, color: "text-indigo-600", bg: "bg-indigo-50" },
    { label: "Content Pieces", value: stats?.total_content_pieces ?? 0, icon: FileText, color: "text-emerald-600", bg: "bg-emerald-50" },
    { label: "Agent Runs", value: stats?.total_agent_runs ?? 0, icon: Zap, color: "text-amber-600", bg: "bg-amber-50" },
    { label: "Running Now", value: stats?.campaigns_running ?? 0, icon: TrendingUp, color: "text-pink-600", bg: "bg-pink-50" },
    { label: "Drafts", value: stats?.content_drafts ?? 0, icon: FileText, color: "text-slate-600", bg: "bg-slate-100" },
  ];

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Dashboard</h1>
        <p className="mt-1 text-slate-500">Your AI agency at a glance</p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {cards.map((card) => (
          <div
            key={card.label}
            className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm"
          >
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-slate-500">{card.label}</p>
              <div className={`rounded-lg ${card.bg} p-2`}>
                <card.icon className={`h-5 w-5 ${card.color}`} />
              </div>
            </div>
            <p className="mt-3 text-3xl font-bold text-slate-900">{card.value}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
