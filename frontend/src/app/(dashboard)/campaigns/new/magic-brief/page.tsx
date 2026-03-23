"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Sparkles, Globe, Loader2, ArrowLeft } from "lucide-react";
import { api, type BrandProfile } from "@/lib/api";
import { cn } from "@/lib/utils";

const MAGIC_BRIEF_STORAGE_KEY = "campaignforge_magic_brief_client";

const TONE_LABELS: Record<string, string> = {
  formality: "Formality",
  humor: "Humor",
  warmth: "Warmth",
  authority: "Authority",
  urgency: "Urgency",
};

export default function MagicBriefPage() {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [profile, setProfile] = useState<BrandProfile | null>(null);

  async function handleScan(e: React.FormEvent) {
    e.preventDefault();
    if (!url.trim()) {
      toast.error("Enter a website URL");
      return;
    }
    setLoading(true);
    setProfile(null);
    try {
      const data = await api.extractBrand(url.trim());
      if (data.error) {
        toast.error(data.error);
        return;
      }
      setProfile(data);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Scan failed");
    } finally {
      setLoading(false);
    }
  }

  function handleUseProfile() {
    if (!profile || profile.error) return;
    const clientDraft = {
      brand_name: profile.brand_name || "New brand",
      industry: profile.industry || "General",
      description: profile.description || "",
      website_url: profile.source_url || url.trim(),
      contact_email: "",
    };
    const brandProfile = {
      voice_description: profile.voice_description || "",
      tone_attributes: profile.tone_attributes ?? {},
      target_audience: profile.target_audience || "",
      style_rules: Array.isArray(profile.style_rules) ? profile.style_rules : [],
      emoji_policy: profile.emoji_policy || "minimal",
    };
    sessionStorage.setItem(
      MAGIC_BRIEF_STORAGE_KEY,
      JSON.stringify({ clientDraft, brandProfile, targetAudienceHint: profile.target_audience || "" })
    );
    toast.success("Profile saved — finish creating your client on the next step");
    router.push("/campaigns/new");
  }

  return (
    <div className="relative min-h-[calc(100vh-8rem)] overflow-hidden rounded-2xl">
      <div
        className="pointer-events-none absolute inset-0 bg-gradient-to-br from-indigo-600/15 via-purple-500/10 to-sky-500/15"
        aria-hidden
      />
      <div className="pointer-events-none absolute -right-24 -top-24 h-96 w-96 rounded-full bg-indigo-400/20 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-32 -left-24 h-80 w-80 rounded-full bg-purple-400/15 blur-3xl" />

      <div className="relative mx-auto max-w-3xl space-y-8 px-1 py-4">
        <div className="flex items-center gap-4">
          <button
            type="button"
            onClick={() => router.back()}
            className="rounded-lg p-2 text-slate-600 transition-colors hover:bg-white/80"
          >
            <ArrowLeft className="h-5 w-5" />
          </button>
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-indigo-600 text-white shadow-sm">
              <Sparkles className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-slate-900">Magic Brief</h1>
              <p className="text-sm text-slate-600">Scan any site — we extract voice, tone, and audience</p>
            </div>
          </div>
        </div>

        <form
          onSubmit={handleScan}
          className="rounded-xl border border-slate-200/80 bg-white/90 p-6 shadow-sm backdrop-blur-sm"
        >
          <label className="mb-2 block text-sm font-medium text-slate-700">Website URL</label>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <div className="relative flex-1">
              <Globe className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://acme.com"
                className="w-full rounded-lg border border-slate-300 py-2.5 pl-10 pr-4 text-slate-900 placeholder-slate-400 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-indigo-500 disabled:opacity-60"
            >
              {loading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Scanning…
                </>
              ) : (
                <>
                  <Sparkles className="h-4 w-4" />
                  Scan Website
                </>
              )}
            </button>
          </div>
        </form>

        {profile && !profile.error && (
          <div className="space-y-6 rounded-xl border border-indigo-100 bg-white/95 p-6 shadow-sm backdrop-blur-sm">
            <div className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-100 pb-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-indigo-600">Brand profile</p>
                <h2 className="mt-1 text-xl font-bold text-slate-900">{profile.brand_name || "Detected brand"}</h2>
                <p className="mt-1 text-sm text-slate-500">{profile.industry}</p>
              </div>
              {profile.source_url && (
                <a
                  href={profile.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm font-medium text-indigo-600 hover:text-indigo-500"
                >
                  View source
                </a>
              )}
            </div>

            {profile.description && (
              <p className="text-sm leading-relaxed text-slate-700">{profile.description}</p>
            )}

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="rounded-xl border border-slate-100 bg-slate-50/80 p-4">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Voice</h3>
                <p className="mt-2 text-sm text-slate-800">{profile.voice_description || "—"}</p>
              </div>
              <div className="rounded-xl border border-slate-100 bg-slate-50/80 p-4">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Target audience</h3>
                <p className="mt-2 text-sm text-slate-800">{profile.target_audience || "—"}</p>
              </div>
            </div>

            {profile.tone_attributes && Object.keys(profile.tone_attributes).length > 0 && (
              <div>
                <h3 className="mb-3 text-sm font-semibold text-slate-900">Tone</h3>
                <div className="space-y-3">
                  {Object.entries(profile.tone_attributes).map(([key, value]) => {
                    const n = Number(value);
                    const pct =
                      Number.isFinite(n) && n > 1
                        ? Math.min(100, Math.max(0, Math.round(n)))
                        : Math.min(100, Math.max(0, Math.round(n * 100)));
                    return (
                      <div key={key}>
                        <div className="mb-1 flex justify-between text-xs text-slate-600">
                          <span>{TONE_LABELS[key] ?? key}</span>
                          <span className="font-medium text-slate-900">{pct}%</span>
                        </div>
                        <div className="h-2 overflow-hidden rounded-full bg-slate-200">
                          <div
                            className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-purple-500 transition-all"
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {profile.style_rules && profile.style_rules.length > 0 && (
              <div>
                <h3 className="mb-2 text-sm font-semibold text-slate-900">Style rules</h3>
                <ul className="space-y-2">
                  {profile.style_rules.map((rule, i) => (
                    <li
                      key={i}
                      className={cn(
                        "flex gap-2 rounded-lg border border-slate-100 bg-white px-3 py-2 text-sm text-slate-700"
                      )}
                    >
                      <span className="font-medium text-indigo-600">{i + 1}.</span>
                      {rule}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <button
              type="button"
              onClick={handleUseProfile}
              className="w-full rounded-lg bg-indigo-600 py-3 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-indigo-500"
            >
              Use This Profile
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
