"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

interface Template {
  id: string;
  name: string;
  description: string;
  category: string;
  channels: string[];
  uses_count: number;
  is_public: boolean;
}

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

  useEffect(() => {
    loadTemplates();
  }, [category]);

  async function loadTemplates() {
    setLoading(true);
    try {
      const data = await api.getTemplates(category === "all" ? undefined : category);
      setTemplates((data.items || []) as Template[]);
    } catch {
      setTemplates([]);
    } finally {
      setLoading(false);
    }
  }

  async function handleLaunch(templateId: string) {
    try {
      await api.launchTemplate(templateId, {});
      router.push(`/campaigns/new?template=${templateId}`);
    } catch (e) {
      console.error(e);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Campaign Templates</h1>
        <p className="mt-1 text-sm text-slate-500">
          Start faster with pre-built campaign templates
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        {CATEGORIES.map((cat) => (
          <button
            key={cat}
            type="button"
            onClick={() => setCategory(cat)}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
              category === cat
                ? "bg-indigo-600 text-white"
                : "border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
            }`}
          >
            {formatCategoryLabel(cat)}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
        </div>
      ) : templates.length === 0 ? (
        <div className="rounded-xl border border-slate-200 bg-white p-12 text-center shadow-sm">
          <p className="text-slate-500">No templates found</p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {templates.map((t) => (
            <div
              key={t.id}
              className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition-colors hover:border-indigo-200"
            >
              <h3 className="text-lg font-semibold text-slate-900">{t.name}</h3>
              <p className="mt-1 line-clamp-2 text-sm text-slate-500">{t.description}</p>
              <div className="mt-3 flex flex-wrap gap-1">
                {(t.channels || []).map((ch) => (
                  <span
                    key={ch}
                    className="rounded-md bg-slate-100 px-2 py-0.5 text-xs text-slate-600"
                  >
                    {ch}
                  </span>
                ))}
              </div>
              <div className="mt-4 flex items-center justify-between">
                <span className="text-xs text-slate-400">{t.uses_count} uses</span>
                <button
                  type="button"
                  onClick={() => handleLaunch(t.id)}
                  className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-indigo-500"
                >
                  Use Template
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
