"use client";

import { useEffect, useState } from "react";
import { api, type DashboardStats } from "@/lib/api";
import { Users, Megaphone, FileText, Zap, TrendingUp } from "lucide-react";
import { PageHeader } from "@/components/ui/panel";
import { StatCard } from "@/components/ui/stat-card";
import { LoadingState } from "@/components/ui/empty-state";

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
    return <LoadingState label="Loading stats" />;
  }

  const cards = [
    { label: "Clients", value: stats?.total_clients ?? 0, icon: Users },
    { label: "Campaigns", value: stats?.total_campaigns ?? 0, icon: Megaphone },
    { label: "Content Pieces", value: stats?.total_content_pieces ?? 0, icon: FileText },
    { label: "Agent Runs", value: stats?.total_agent_runs ?? 0, icon: Zap },
    { label: "Running Now", value: stats?.campaigns_running ?? 0, icon: TrendingUp, tone: "accent" as const },
    { label: "Drafts", value: stats?.content_drafts ?? 0, icon: FileText },
  ];

  return (
    <div className="space-y-8">
      <PageHeader eyebrow="Overview" title="Dashboard" description="Your AI agency at a glance" />

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {cards.map((card, i) => (
          <StatCard
            key={card.label}
            label={card.label}
            value={card.value}
            icon={card.icon}
            tone={card.tone}
            delay={i * 0.05}
          />
        ))}
      </div>
    </div>
  );
}
