"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, TEMPLATE_CATEGORIES, templateCategoryLabel } from "@/lib/api";
import { LayoutTemplate } from "lucide-react";
import { platformLabel } from "@/lib/platforms";
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
 * NOTE ON PLACEMENT: this tab lives in the **Ads** nav group (260925, by request),
 * but these are CAMPAIGN templates (`campaign_template` rows) -- Use Template fills
 * the campaign form and routes to /campaigns/new, not the Ads generator. Nothing
 * ads-specific was invented for it; there is no ad-creative template library.
 *
 * CF-14: one taxonomy, shared with the card labels and db/seed.sql. The tabs
 * used to list categories no template had, so "Social" and "Thought Leadership"
 * always came back empty, while Recurring, B2B and Events had no tab at all.
 */
const CATEGORIES = ["all", ...TEMPLATE_CATEGORIES.map((c) => c.id)];

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
    // Recording the use is worth doing but must not block the navigation — the
    // form reads the template itself from the id in the URL (CF-14).
    try {
      await api.launchTemplate(templateId, {});
    } catch {
      // uses_count is a nicety; failing to bump it is no reason to refuse.
    }
    router.push(`/campaigns/new?template=${templateId}`);
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
        items={CATEGORIES.map((cat) => ({
          id: cat,
          label: cat === "all" ? "All" : templateCategoryLabel(cat),
        }))}
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
                <span className="font-mono text-[11px] text-accent-text">
                  {templateCategoryLabel(t.category)}
                </span>
              )}
              <h3 className="mt-1.5 font-display text-lg font-semibold text-ink">{t.name}</h3>
              <p className="mt-1 line-clamp-2 flex-1 text-sm text-muted">{t.description}</p>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {(t.channels || []).map((ch) => (
                  <Tag key={ch}>{platformLabel(ch)}</Tag>
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
