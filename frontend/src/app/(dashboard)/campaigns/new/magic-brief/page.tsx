"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Sparkles, Globe, Loader2, ArrowLeft, ArrowUpRight } from "lucide-react";
import { api, type BrandProfile } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Eyebrow } from "@/components/ui/panel";
import { controlClass } from "@/components/ui/field";
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
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="flex items-start gap-3">
        <button
          type="button"
          onClick={() => router.back()}
          aria-label="Go back"
          className="press-scale mt-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-line text-muted transition-colors hover:border-slate-300 hover:text-ink"
        >
          <ArrowLeft className="h-4 w-4" />
        </button>
        <div className="space-y-1.5">
          <Eyebrow>Create · Brand intake</Eyebrow>
          <h1 className="font-display text-2xl font-semibold tracking-tight text-ink sm:text-3xl">Magic Brief</h1>
          <p className="text-sm text-muted">Scan any site — we extract voice, tone, and audience</p>
        </div>
      </div>

      {/* The dashed "working surface" from Cadence's intake flow, with a soft amber glow. */}
      <form
        onSubmit={handleScan}
        className="relative overflow-hidden rounded-xl border border-dashed border-slate-300 bg-panel/50 p-6 backdrop-blur-xl motion-safe:animate-screen-in sm:p-8"
      >
        <div
          aria-hidden
          className="pointer-events-none absolute -right-20 -top-24 h-64 w-64 rounded-full bg-accent/15 blur-3xl"
        />
        <label htmlFor="magic-brief-url" className="relative mb-2 block text-xs font-medium text-muted">
          Website URL
        </label>
        <div className="relative flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="relative flex-1">
            <Globe className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
            <input
              id="magic-brief-url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://acme.com"
              className={cn(controlClass, "pl-10 font-mono")}
            />
          </div>
          <Button type="submit" disabled={loading} className="py-2.5">
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
          </Button>
        </div>
        {loading && (
          <div className="relative mt-4 h-1 overflow-hidden rounded-full bg-slate-200" aria-hidden>
            <div className="h-full w-1/3 animate-pulse rounded-full bg-accent" />
          </div>
        )}
      </form>

      {profile && !profile.error && (
        <div className="space-y-6 rounded-xl border border-line bg-panel/70 p-6 shadow-[0_0_40px_rgb(var(--c-accent)/0.1)] backdrop-blur-xl motion-safe:animate-screen-in sm:p-8">
          <div className="flex flex-wrap items-start justify-between gap-4 border-b border-line pb-5">
            <div className="space-y-1.5">
              <Eyebrow>Brand profile</Eyebrow>
              <h2 className="font-display text-2xl font-semibold tracking-tight text-ink">
                {profile.brand_name || "Detected brand"}
              </h2>
              <p className="text-sm text-muted">{profile.industry}</p>
            </div>
            {profile.source_url && (
              <a
                href={profile.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 font-mono text-xs text-accent-text hover:underline"
              >
                View source
                <ArrowUpRight className="h-3.5 w-3.5" />
              </a>
            )}
          </div>

          {profile.description && (
            <p className="text-sm leading-relaxed text-ink">{profile.description}</p>
          )}

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="border-l-2 border-accent/60 py-1 pl-4">
              <h3 className="font-mono text-[11px] text-muted">Voice</h3>
              <p className="mt-1.5 text-sm text-ink">{profile.voice_description || "—"}</p>
            </div>
            <div className="border-l-2 border-line py-1 pl-4">
              <h3 className="font-mono text-[11px] text-muted">Target audience</h3>
              <p className="mt-1.5 text-sm text-ink">{profile.target_audience || "—"}</p>
            </div>
          </div>

          {profile.tone_attributes && Object.keys(profile.tone_attributes).length > 0 && (
            <div>
              <h3 className="mb-3 text-sm font-semibold text-ink">Tone</h3>
              <div className="space-y-3">
                {Object.entries(profile.tone_attributes).map(([key, value]) => {
                  const n = Number(value);
                  const pct =
                    Number.isFinite(n) && n > 1
                      ? Math.min(100, Math.max(0, Math.round(n)))
                      : Math.min(100, Math.max(0, Math.round(n * 100)));
                  return (
                    <div key={key}>
                      <div className="mb-1 flex justify-between text-xs text-muted">
                        <span>{TONE_LABELS[key] ?? key}</span>
                        <span className="font-mono font-medium text-ink">{pct}%</span>
                      </div>
                      <div className="h-1.5 overflow-hidden rounded-full bg-slate-200">
                        <div
                          className="h-full rounded-full bg-gradient-to-r from-[#E4A72E] to-accent transition-all duration-700"
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
              <h3 className="mb-2 text-sm font-semibold text-ink">Style rules</h3>
              <ul className="space-y-2">
                {profile.style_rules.map((rule, i) => (
                  <li
                    key={i}
                    className="flex gap-3 rounded-lg border border-line bg-canvas/40 px-3 py-2 text-sm text-ink"
                  >
                    <span className="font-mono text-xs leading-5 text-accent-text">
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    {rule}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <Button onClick={handleUseProfile} className="w-full py-3">
            Use This Profile
          </Button>
        </div>
      )}
    </div>
  );
}
