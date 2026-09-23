"use client";

/*
 * Cadence's SettingsScreen tabs, scoped to the active client: Profile, Accounts,
 * Posting preferences, Plan & usage, Activity log and Export. The existing
 * workspace tabs (Workspace, API keys, Notifications) stay alongside in
 * settings/page.tsx.
 *
 * Deliberately not ported: Cadence's "Reset this product's data" (destructive,
 * and there is no undo on the server) and its simulated connect/upgrade flows —
 * Accounts links to the real OAuth screen, Plan links to the real Stripe pricing.
 */

import { useCallback, useEffect, useState, type ComponentType } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  CheckCircle2,
  FileText,
  Layers,
  Link2,
  ListChecks,
  Loader2,
  PenLine,
  Rocket,
  Send,
  Sparkle,
  Sparkles,
  Trash2,
} from "lucide-react";
import { api, type Client } from "@/lib/api";
import type { ClientOverview } from "@/lib/api-foundation";
import {
  CADENCE_OPTIONS,
  VOICE_OPTIONS,
  insightsApi,
  timeAgo,
  type ActivityItem,
  type ClientExport,
  type PostingPrefs,
} from "@/lib/api-insights";
import { trackFeature } from "@/lib/analytics";
import { Button, buttonVariants } from "@/components/ui/button";
import { SectionCard } from "@/components/ui/section-card";
import { ErrorBanner } from "@/components/ui/feedback";
import { LoadingState } from "@/components/ui/empty-state";
import { UsageMeter } from "@/components/insights/bars";
import { cn } from "@/lib/utils";

export function ProfileTab({ client }: { client: ClientOverview }) {
  const [detail, setDetail] = useState<Client | null>(null);
  const [error, setError] = useState(false);

  const load = useCallback(() => {
    setError(false);
    api
      .getClient(client.id)
      .then(setDetail)
      .catch(() => setError(true));
  }, [client.id]);

  useEffect(load, [load]);

  const rows: [string, string | null | undefined][] = [
    ["Client name", detail?.brand_name ?? client.brand_name],
    ["Website", detail?.website_url ?? client.website_url],
    ["Industry", detail?.industry],
    ["Contact email", detail?.contact_email],
    ["Description", detail?.description],
  ];

  return (
    <SectionCard eyebrow="Client profile" title={client.brand_name}>
      {error && <ErrorBanner message="Couldn't load this client's details." onRetry={load} />}
      <dl className="space-y-3">
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt className="text-[11px] font-medium text-muted">{label}</dt>
            <dd className={cn("mt-0.5 text-[13px]", value ? "text-ink" : "text-muted")}>{value || "Not set"}</dd>
          </div>
        ))}
        <div>
          <dt className="text-[11px] font-medium text-muted">Brand profile</dt>
          <dd className="mt-0.5 flex items-center gap-1.5 text-[13px]">
            {client.has_brand_profile ? (
              <span className="flex items-center gap-1.5 text-emerald-700">
                <CheckCircle2 className="h-3.5 w-3.5" /> Set up
              </span>
            ) : (
              <span className="text-muted">Not set up yet — generators need it for the voice</span>
            )}
          </dd>
        </div>
      </dl>
      <div className="mt-5 flex flex-wrap gap-2 border-t border-line pt-4">
        <Link href={`/clients/${client.id}`} className={buttonVariants()}>
          Edit client details
        </Link>
        <Link href="/setup/profile" className={buttonVariants({ variant: "secondary" })}>
          {client.has_brand_profile ? "Edit brand profile" : "Set up brand profile"}
        </Link>
      </div>
    </SectionCard>
  );
}

export function AccountsTab({ client }: { client: ClientOverview }) {
  return (
    <SectionCard eyebrow="Connected accounts" title="Social accounts">
      <p className="text-sm text-muted">
        {client.brand_name} has{" "}
        <span className="font-medium text-ink">
          {client.connected_accounts} connected account{client.connected_accounts === 1 ? "" : "s"}
        </span>
        . Connecting and disconnecting happens in Setup › Accounts, through each platform&apos;s real login.
      </p>
      <Link href="/setup/accounts" className={cn(buttonVariants(), "mt-4")}>
        <Link2 className="h-4 w-4" /> Manage accounts
      </Link>
      <p className="mt-4 font-mono text-[11px] text-muted">
        Publishing is real for X, LinkedIn and Facebook — posts go to the live account once you approve and
        schedule them. Instagram and TikTok publishing isn&apos;t available.
      </p>
    </SectionCard>
  );
}

export function PostingTab({ client }: { client: ClientOverview }) {
  const [prefs, setPrefs] = useState<PostingPrefs>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<"load" | "save" | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setPrefs((await insightsApi.getPostingPrefs(client.id)).posting_prefs);
    } catch {
      setError("load");
    } finally {
      setLoading(false);
    }
  }, [client.id]);

  useEffect(() => {
    void load();
  }, [load]);

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const res = await insightsApi.setPostingPrefs(client.id, {
        voice_register: prefs.voice_register,
        cadence_per_week: prefs.cadence_per_week,
      });
      setPrefs(res.posting_prefs);
      setSaved(true);
      setTimeout(() => setSaved(false), 1800);
    } catch {
      setError("save");
    } finally {
      setSaving(false);
    }
  };

  return (
    <SectionCard eyebrow="Posting preferences" title={`How ${client.brand_name} posts`}>
      <div className="space-y-5">
        <div className="flex items-center gap-3 rounded-lg border border-emerald-300 bg-emerald-50 p-4">
          <div className="flex-1">
            <div className="text-[13.5px] font-medium text-ink">Human approval before publishing</div>
            <div className="mt-1 max-w-md text-[11.5px] leading-normal text-muted">
              Nothing CampaignForge drafts ever goes out on its own — every post lands in Pending and needs your
              explicit Approve click, after moderation. This isn&apos;t a setting because it isn&apos;t a
              trade-off we offer.
            </div>
          </div>
          <span className="flex shrink-0 items-center gap-1.5 rounded px-2.5 py-1 text-[10.5px] font-semibold text-emerald-700">
            <CheckCircle2 className="h-3 w-3" /> ALWAYS ON
          </span>
        </div>

        {loading ? (
          <LoadingState className="h-24" />
        ) : error === "load" ? (
          <ErrorBanner message="Couldn't load posting preferences." onRetry={() => void load()} />
        ) : (
          <>
            <div>
              <div className="mb-1.5 text-[13.5px] font-medium text-ink">Voice register</div>
              <div className="grid gap-2 sm:grid-cols-2">
                {VOICE_OPTIONS.map((opt) => {
                  const on = prefs.voice_register === opt;
                  return (
                    <button
                      key={opt}
                      type="button"
                      aria-pressed={on}
                      onClick={() => setPrefs((p) => ({ ...p, voice_register: opt }))}
                      className={cn(
                        "press-scale rounded-md border px-3 py-2 text-left text-[12.5px] font-medium transition-colors duration-200",
                        on ? "border-accent bg-accent/10 text-accent-text" : "border-line bg-canvas/40 text-muted hover:text-ink"
                      )}
                    >
                      {opt}
                    </button>
                  );
                })}
              </div>
            </div>

            <div>
              <div className="mb-2 text-[13.5px] font-medium text-ink">Posting cadence</div>
              <div className="flex flex-wrap gap-2">
                {CADENCE_OPTIONS.map((n) => {
                  const on = prefs.cadence_per_week === n;
                  return (
                    <button
                      key={n}
                      type="button"
                      aria-pressed={on}
                      onClick={() => setPrefs((p) => ({ ...p, cadence_per_week: n }))}
                      className={cn(
                        "rounded-md border px-3 py-2 text-[12.5px] font-medium transition-colors duration-200",
                        on ? "border-accent bg-accent/15 text-accent-text" : "border-line bg-canvas/40 text-muted hover:text-ink"
                      )}
                    >
                      {n}/week
                    </button>
                  );
                })}
              </div>
            </div>

            <p className="text-[11.5px] leading-normal text-muted">
              Every generator reads these as part of {client.brand_name}&apos;s brand context. Nothing is
              scheduled automatically from the cadence — it only steers how much and how the drafts are written.
            </p>

            <div className="flex items-center gap-3">
              <Button onClick={() => void save()} disabled={saving}>
                {saving && <Loader2 className="h-4 w-4 animate-spin" />}
                Save changes
              </Button>
              {saved && (
                <span className="flex items-center gap-1.5 text-xs font-medium text-emerald-700 motion-safe:animate-screen-in">
                  <CheckCircle2 className="h-3.5 w-3.5" /> Saved
                </span>
              )}
            </div>
            {error === "save" && <ErrorBanner message="Couldn't save — try again." onRetry={() => void save()} />}
          </>
        )}
      </div>
    </SectionCard>
  );
}

interface Usage {
  plan_tier: string;
  status?: string;
  generations_used?: number;
  generations_limit?: number;
  posts_used?: number;
  posts_limit?: number;
  features?: string[];
}

export function PlanTab() {
  const [usage, setUsage] = useState<Usage | null>(null);
  const [error, setError] = useState(false);

  const load = useCallback(() => {
    setError(false);
    api
      .getSubscription()
      .then((s) => setUsage(s as Usage))
      .catch(() => setError(true));
  }, []);

  useEffect(load, [load]);

  if (error) return <ErrorBanner message="Couldn't load your plan." onRetry={load} />;
  if (!usage) return <LoadingState className="h-40" />;

  const genKnown = usage.generations_used != null && usage.generations_limit != null;
  return (
    <SectionCard eyebrow="Plan & usage" title={`${usage.plan_tier.charAt(0).toUpperCase()}${usage.plan_tier.slice(1)} plan`}>
      <div className="mb-4 rounded-xl border border-line bg-canvas/40 p-5">
        {genKnown ? (
          <>
            <div className="flex items-baseline gap-2">
              <span className="font-display text-[32px] font-semibold tabular-nums text-accent-text">
                {usage.generations_used}
              </span>
              <span className="font-display text-lg text-muted">/{usage.generations_limit}</span>
            </div>
            <div className="mt-1 text-[11.5px] text-muted">generations used this billing period</div>
          </>
        ) : (
          <div className="text-sm text-muted">Generation usage isn&apos;t available for this workspace.</div>
        )}
      </div>
      <div className="space-y-2">
        <UsageMeter label="AI generations" used={usage.generations_used} limit={usage.generations_limit} upgradeHref="/pricing" />
        <UsageMeter label="Published posts" used={usage.posts_used} limit={usage.posts_limit} upgradeHref="/pricing" delay={0.05} />
      </div>
      <p className="mt-3 text-[11.5px] italic leading-relaxed text-muted">
        One generation is one generate click that returned something usable (an Amplify pack, a blog post,
        an advocacy pack…). Failed generations aren&apos;t charged. Both counters reset when your plan renews.
      </p>
      {usage.features && usage.features.length > 0 && (
        <ul className="mt-4 space-y-1.5">
          {usage.features.map((f) => (
            <li key={f} className="flex items-start gap-1.5 text-[11.5px] text-slate-600">
              <CheckCircle2 className="mt-0.5 h-3 w-3 shrink-0 text-accent-text" /> {f}
            </li>
          ))}
        </ul>
      )}
      <Link href="/pricing" className={cn(buttonVariants({ variant: "secondary" }), "mt-5")}>
        Compare plans
      </Link>
    </SectionCard>
  );
}

const ACTIVITY_ICON_META: Record<string, { icon: ComponentType<{ className?: string }>; tone: string }> = {
  "profile.updated": { icon: Sparkles, tone: "border-accent/40 text-accent-text" },
  "account.connected": { icon: Link2, tone: "border-emerald-300 text-emerald-600" },
  "post.created": { icon: PenLine, tone: "border-line text-muted" },
  "post.approved": { icon: CheckCircle2, tone: "border-emerald-300 text-emerald-600" },
  "post.scheduled": { icon: CheckCircle2, tone: "border-sky-300 text-sky-600" },
  "post.published": { icon: Send, tone: "border-emerald-300 text-emerald-600" },
  "post.failed": { icon: AlertTriangle, tone: "border-red-300 text-red-600" },
  "post.rejected": { icon: Trash2, tone: "border-red-300 text-red-600" },
  "moderation.flagged": { icon: AlertTriangle, tone: "border-accent/40 text-accent-text" },
  "moderation.overridden": { icon: AlertTriangle, tone: "border-accent/40 text-accent-text" },
  "asset.created": { icon: FileText, tone: "border-accent/40 text-accent-text" },
  "pack.generated": { icon: Layers, tone: "border-accent/40 text-accent-text" },
  "campaign.created": { icon: Rocket, tone: "border-accent/40 text-accent-text" },
};

export function ActivityTab({ client }: { client: ClientOverview }) {
  const [items, setItems] = useState<ActivityItem[] | null>(null);
  const [error, setError] = useState(false);

  const load = useCallback(() => {
    setError(false);
    insightsApi
      .activity(client.id)
      .then((r) => setItems(r.items))
      .catch(() => setError(true));
  }, [client.id]);

  useEffect(load, [load]);

  return (
    <SectionCard eyebrow="Activity log" title={`What happened for ${client.brand_name}`}>
      <p className="mb-4 text-[11.5px] leading-relaxed text-muted">
        A record of the meaningful things that happened to this client — connections, drafts, approvals,
        moderation flags, publishes. Built from the real records; the last 50 events.
      </p>
      {error ? (
        <ErrorBanner message="Couldn't load the activity log." onRetry={load} />
      ) : items === null ? (
        <LoadingState className="h-32" />
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-slate-300 py-14 text-muted">
          <ListChecks className="h-5 w-5" />
          <span className="text-[12.5px]">Nothing logged yet</span>
        </div>
      ) : (
        <div className="space-y-2">
          {items.map((entry, i) => {
            const meta = ACTIVITY_ICON_META[entry.action] ?? { icon: Sparkle, tone: "border-line text-muted" };
            const Icon = meta.icon;
            return (
              <div
                key={entry.id}
                className="flex items-center gap-3 rounded-md border border-line bg-canvas/40 px-3 py-2.5 motion-safe:animate-screen-in"
                style={{ animationDelay: `${Math.min(i * 0.03, 0.3)}s` }}
              >
                <div className={cn("flex h-7 w-7 shrink-0 items-center justify-center rounded-md border", meta.tone)}>
                  <Icon className="h-3.5 w-3.5" />
                </div>
                <span className="min-w-0 flex-1 text-[12.5px] text-slate-600">{entry.detail}</span>
                <time dateTime={entry.at} title={new Date(entry.at).toLocaleString()} className="shrink-0 font-mono text-[10px] text-muted">
                  {timeAgo(entry.at)}
                </time>
              </div>
            );
          })}
        </div>
      )}
    </SectionCard>
  );
}

const EXPORT_SECTIONS: { key: string; label: string }[] = [
  { key: "posts", label: "Posts (queue + published)" },
  { key: "creative_assets", label: "Creative assets" },
  { key: "repurpose_packs", label: "Repurpose packs (Amplify)" },
  { key: "campaigns", label: "Campaigns" },
  { key: "connected_accounts", label: "Connected accounts" },
];

export function ExportTab({ client }: { client: ClientOverview }) {
  const [data, setData] = useState<ClientExport | null>(null);
  const [error, setError] = useState(false);

  const load = useCallback(() => {
    setError(false);
    insightsApi
      .exportClient(client.id)
      .then(setData)
      .catch(() => setError(true));
  }, [client.id]);

  useEffect(load, [load]);

  const counts = data?.counts ?? {};
  const totalItems = (counts.posts ?? 0) + (counts.creative_assets ?? 0) + (counts.repurpose_packs ?? 0);
  const hasBrand = Boolean(data?.brand_profile);

  const download = () => {
    if (!data) return;
    const slug = client.brand_name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "client";
    const date = new Date().toISOString().slice(0, 10);
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `campaignforge-${slug}-${date}.json`;
    a.click();
    URL.revokeObjectURL(url);
    trackFeature("settings-export");
  };

  return (
    <SectionCard eyebrow="Export" title="Export your content">
      <p className="mb-4 text-[11.5px] leading-relaxed text-muted">
        Download everything stored for {client.brand_name} as a single JSON file — client profile and setup
        (campaign focus, posting preferences), brand profile, every post with its status and moderation record,
        every saved creative asset (blog posts, emails, launch kits, ad sets, advocacy packs…), Amplify pack
        history, campaigns and connected accounts (never their tokens).
      </p>
      {error ? (
        <ErrorBanner message="Couldn't prepare the export." onRetry={load} />
      ) : !data ? (
        <LoadingState className="h-32" />
      ) : (
        <div>
          <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-3">
            {EXPORT_SECTIONS.map(({ key, label }) => (
              <div key={key} className="rounded-md border border-line bg-canvas/40 p-3">
                <div className={cn("font-display text-[19px] font-semibold tabular-nums", counts[key] ? "text-ink" : "text-muted")}>
                  {counts[key] ?? 0}
                </div>
                <div className="mt-0.5 text-[10.5px] text-muted">{label}</div>
              </div>
            ))}
            <div className="rounded-md border border-line bg-canvas/40 p-3">
              <div className={cn("font-display text-[19px] font-semibold", hasBrand ? "text-ink" : "text-muted")}>
                {hasBrand ? "Yes" : "No"}
              </div>
              <div className="mt-0.5 text-[10.5px] text-muted">Brand profile</div>
            </div>
          </div>
          {totalItems > 0 || hasBrand ? (
            <Button onClick={download}>
              <FileText className="h-3.5 w-3.5" /> Download all ({totalItems} items) as .json
            </Button>
          ) : (
            <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-slate-300 py-10 text-muted">
              <FileText className="h-5 w-5" />
              <span className="text-[12.5px]">Nothing generated yet — create some content first</span>
              <Link href="/create/content" className="text-xs font-medium text-accent-text underline">
                Go to Create
              </Link>
            </div>
          )}
        </div>
      )}
    </SectionCard>
  );
}
