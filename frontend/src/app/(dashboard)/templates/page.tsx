"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { LayoutTemplate } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/panel";
import { EmptyState, LoadingState } from "@/components/ui/empty-state";
import { SegmentedTabs, Tag } from "@/components/ui/tabs";

interface Template {
  id: string;
  name: string;
  description: string;
  category: string;
  channels: string[];
  uses_count: number;
  is_public: boolean;
}

/*
 * These are CAMPAIGN templates (campaign_template rows), not ad-creative templates --
 * launching one routes to /campaigns/new, not to the Ads generator. The tab lives in
 * the Ads group because that is where it was asked for; nothing ads-specific has been
 * invented for it, and the seeded categories below are the ones that actually exist.
 */
const CATEGORIES = ["all", "launch", "social", "awareness", "seasonal", "thought-leadership"];

function formatCategoryLabel(cat: string) {
  if (cat === "all") return "All";
  return cat.replace(/-/g, " ").replace(/\b\w/g, (l) => l.toUpperCase());
}

export default function TemplatesPage() {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [category, setCategory] = useState("all");
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  const loadTemplates = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.getTemplates(category === "all" ? undefined : category);
      setTemplates((data.items || []) as Template[]);
    } catch {
      setTemplates([]);
    } finally {
      setLoading(false);
    }
  }, [category]);

  useEffect(() => {
    loadTemplates();
  }, [loadTemplates]);

  async function handleLaunch(templateId: string) {
    try {
      await api.launchTemplate(templateId, {});
      router.push(`/campaigns/new?template=${templateId}`);
    } catch (e) {
      console.error(e);
    }
  }

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Ads"
        title="Campaign Templates"
        description="Start faster with pre-built campaign templates"
      />

      <SegmentedTabs
        label="Template categories"
        value={category}
        onChange={setCategory}
        items={CATEGORIES.map((cat) => ({ id: cat, label: formatCategoryLabel(cat) }))}
      />

      {loading ? (
        <LoadingState label="Loading templates" className="h-48" />
      ) : templates.length === 0 ? (
        <EmptyState icon={LayoutTemplate} title="No templates found" />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {templates.map((t, i) => (
            <div
              key={t.id}
              style={{ animationDelay: `${Math.min(i, 8) * 0.05}s` }}
              className="group flex flex-col rounded-xl border border-line bg-panel/70 p-5 shadow-soft backdrop-blur-xl transition-[transform,border-color] duration-200 hover:-translate-y-0.5 hover:border-accent/50 motion-safe:animate-screen-in"
            >
              {t.category && (
                <span className="font-mono text-[11px] capitalize text-accent-text">
                  {t.category.replace(/-/g, " ")}
                </span>
              )}
              <h3 className="mt-1.5 font-display text-lg font-semibold text-ink">{t.name}</h3>
              <p className="mt-1 line-clamp-2 flex-1 text-sm text-muted">{t.description}</p>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {(t.channels || []).map((ch) => (
                  <Tag key={ch}>{ch}</Tag>
                ))}
              </div>
              <div className="mt-4 flex items-center justify-between border-t border-line pt-3">
                <span className="font-mono text-[11px] text-muted">{t.uses_count} uses</span>
                <Button size="sm" onClick={() => handleLaunch(t.id)}>
                  Use Template
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
