"use client";

import { Suspense, useCallback, useEffect, useState, type ElementType } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Settings,
  Key,
  Bell,
  Save,
  Plus,
  Trash2,
  Loader2,
  AlertTriangle,
  UserRound,
  Link2,
  CalendarClock,
  Gauge,
  ListChecks,
  Download,
  Users,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Eyebrow, PageHeader } from "@/components/ui/panel";
import { Field, Input, Select } from "@/components/ui/field";
import { EmptyState, LoadingState, Notice } from "@/components/ui/empty-state";
import { buttonVariants } from "@/components/ui/button";
import { useActiveClient } from "@/lib/active-client";
import Link from "next/link";
import {
  AccountsTab,
  ActivityTab,
  ExportTab,
  PlanTab,
  PostingTab,
  ProfileTab,
} from "@/components/settings/cadence-settings";

/*
 * Cadence's tabs (per active client) first, then the workspace-wide tabs that
 * predate the port. `?tab=platforms` is the old deep link for connected
 * accounts; it now resolves to the Accounts tab, which links to Setup › Accounts
 * (the real OAuth screen) rather than duplicating it.
 */
type Tab =
  | "profile"
  | "accounts"
  | "posting"
  | "plan"
  | "activity"
  | "export"
  | "general"
  | "api-keys"
  | "notifications";

const TABS: readonly Tab[] = [
  "profile",
  "accounts",
  "posting",
  "plan",
  "activity",
  "export",
  "general",
  "api-keys",
  "notifications",
];

const CLIENT_TABS: ReadonlySet<Tab> = new Set<Tab>(["profile", "accounts", "posting", "activity", "export"]);

const TAB_ALIASES: Record<string, Tab> = { platforms: "accounts" };

function resolveTab(value: string | null): Tab {
  if (value && TAB_ALIASES[value]) return TAB_ALIASES[value];
  return TABS.includes(value as Tab) ? (value as Tab) : "profile";
}

interface ApiKeyRow {
  id: string;
  label: string;
  prefix: string;
  created: string;
}

function apiKeyRowFromApi(row: unknown): ApiKeyRow | null {
  const r = row as Record<string, unknown>;
  const id = r.id != null ? String(r.id) : "";
  if (!id) return null;
  const createdRaw = r.created_at;
  const created =
    typeof createdRaw === "string"
      ? createdRaw.slice(0, 10)
      : new Date().toISOString().slice(0, 10);
  return {
    id,
    label: String(r.name ?? r.label ?? "API Key"),
    prefix: String(r.key_prefix ?? r.prefix ?? "cf_"),
    created,
  };
}

// Planned notification types. There is no delivery mechanism and no persistence
// behind any of them: nothing in the backend calls `create_notification()`, and
// no endpoint stores these preferences. They are listed (disabled) so the roadmap
// is visible, not rendered as working switches — the previous version showed
// live-looking toggles whose state was lost on every reload.
const PLANNED_NOTIFICATION_TYPES = [
  {
    id: "campaign_completed",
    label: "Campaign completed",
    desc: "Notify when a campaign pipeline finishes",
  },
  {
    id: "content_review",
    label: "Content ready for review",
    desc: "Alert when content needs human approval",
  },
  {
    id: "publishing_success",
    label: "Publishing success",
    desc: "Confirmation when content is published to platforms",
  },
  {
    id: "weekly_digest",
    label: "Weekly performance digest",
    desc: "Summary of campaign performance metrics",
  },
] as const;

export default function SettingsPage() {
  // useSearchParams needs a Suspense boundary to keep the route prerenderable.
  return (
    <Suspense>
      <SettingsContent />
    </Suspense>
  );
}

function SettingsContent() {
  // The active tab lives in the URL (?tab=platforms) so the app nav can deep-link
  // Setup › Accounts here and highlight the right group.
  const router = useRouter();
  const tabParam = useSearchParams().get("tab");
  const activeTab: Tab = resolveTab(tabParam);
  const setActiveTab = (tab: Tab) =>
    router.replace(tab === "profile" ? "/settings" : `/settings?tab=${tab}`, { scroll: false });
  const { active, loading: clientsLoading } = useActiveClient();
  const [orgName, setOrgName] = useState("");
  const [domain, setDomain] = useState("");
  const [timezone, setTimezone] = useState("UTC");
  const [settingsExtra, setSettingsExtra] = useState<Record<string, unknown>>({});
  const [generalLoading, setGeneralLoading] = useState(true);
  const [generalSaving, setGeneralSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [apiKeys, setApiKeys] = useState<ApiKeyRow[]>([]);
  const [keysLoading, setKeysLoading] = useState(false);
  const [keysBusy, setKeysBusy] = useState(false);

  const loadGeneral = useCallback(async () => {
    setGeneralLoading(true);
    try {
      const data = await api.getSettings();
      setOrgName(data.name ?? "");
      setDomain(data.domain ?? "");
      const s = (data.settings ?? {}) as Record<string, unknown>;
      setSettingsExtra(s);
      const tz = s.timezone ?? s.default_timezone;
      setTimezone(typeof tz === "string" ? tz : "UTC");
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Failed to load settings");
    } finally {
      setGeneralLoading(false);
    }
  }, []);

  const loadApiKeys = useCallback(async () => {
    setKeysLoading(true);
    try {
      const res = await api.getApiKeys();
      const rows = (res.items ?? []).map(apiKeyRowFromApi).filter(Boolean) as ApiKeyRow[];
      setApiKeys(rows);
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Failed to load API keys");
    } finally {
      setKeysLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadGeneral();
  }, [loadGeneral]);

  useEffect(() => {
    if (activeTab === "api-keys") void loadApiKeys();
  }, [activeTab, loadApiKeys]);

  const tabs: { id: Tab; label: string; icon: ElementType }[] = [
    { id: "profile", label: "Client profile", icon: UserRound },
    { id: "accounts", label: "Connected accounts", icon: Link2 },
    { id: "posting", label: "Posting preferences", icon: CalendarClock },
    { id: "plan", label: "Plan & usage", icon: Gauge },
    { id: "activity", label: "Activity log", icon: ListChecks },
    { id: "export", label: "Export", icon: Download },
    { id: "general", label: "Workspace", icon: Settings },
    { id: "api-keys", label: "API Keys", icon: Key },
    { id: "notifications", label: "Notifications", icon: Bell },
  ];

  const handleSaveGeneral = async () => {
    setGeneralSaving(true);
    try {
      await api.updateSettings({
        name: orgName,
        domain,
        settings: { ...settingsExtra, timezone },
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
      toast.success("Settings saved");
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Save failed");
    } finally {
      setGeneralSaving(false);
    }
  };

  const handleCreateApiKey = async () => {
    const name = window.prompt("Name for this API key", "Integration");
    if (name === null) return;
    const trimmed = name.trim() || "Integration";
    setKeysBusy(true);
    try {
      await api.createApiKey(trimmed, ["read", "write"]);
      toast.success("API key created");
      await loadApiKeys();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Could not create key");
    } finally {
      setKeysBusy(false);
    }
  };

  const handleRevokeApiKey = async (id: string, label: string) => {
    if (!window.confirm(`Revoke API key "${label}"? This cannot be undone.`)) return;
    setKeysBusy(true);
    try {
      await api.revokeApiKey(id);
      toast.success("Key revoked");
      await loadApiKeys();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Could not revoke key");
    } finally {
      setKeysBusy(false);
    }
  };

  return (
    <div className="space-y-8">
      <PageHeader eyebrow="Settings" title="Settings" description="The active client's profile, posting preferences, activity and export — plus plan, workspace and integration settings." />

      <div className="grid gap-6 lg:grid-cols-[230px_minmax(0,1fr)]">
        {/* Left tab list on desktop (Cadence settings layout); a scrollable row on mobile. */}
        <div
          role="group"
          aria-label="Settings sections"
          className="flex gap-1 overflow-x-auto rounded-lg border border-line bg-panel/60 p-1 backdrop-blur-xl lg:flex-col lg:self-start lg:overflow-visible lg:border-0 lg:bg-transparent lg:p-0 lg:backdrop-blur-none"
        >
          {tabs.map((tab) => {
            const active = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                aria-pressed={active}
                onClick={() => setActiveTab(tab.id)}
                className={cn(
                  "press-scale flex shrink-0 items-center gap-2 whitespace-nowrap rounded-md border px-3 py-2 text-left text-sm font-medium transition-colors duration-200 lg:w-full lg:py-2.5",
                  active
                    ? "border-accent/50 bg-accent/10 text-ink lg:shadow-[inset_2px_0_0_rgb(var(--c-accent))]"
                    : "border-transparent text-muted hover:bg-slate-500/10 hover:text-ink"
                )}
              >
                <tab.icon className={cn("h-4 w-4", active && "text-accent-text")} />
                {tab.label}
              </button>
            );
          })}
        </div>

        {CLIENT_TABS.has(activeTab) || activeTab === "plan" ? (
          <div key={`${activeTab}-${active?.id ?? "none"}`} className="min-w-0 space-y-5">
            {activeTab === "plan" ? (
              <PlanTab />
            ) : clientsLoading ? (
              <LoadingState label="Loading clients" className="h-40" />
            ) : !active ? (
              <EmptyState
                icon={Users}
                title="No client yet"
                description="These settings belong to a client. Add one first."
                action={
                  <Link href="/clients?new=1" className={buttonVariants()}>
                    Add a client
                  </Link>
                }
              />
            ) : activeTab === "profile" ? (
              <ProfileTab client={active} />
            ) : activeTab === "accounts" ? (
              <AccountsTab client={active} />
            ) : activeTab === "posting" ? (
              <PostingTab client={active} />
            ) : activeTab === "activity" ? (
              <ActivityTab client={active} />
            ) : (
              <ExportTab client={active} />
            )}
            <p className="px-1 font-mono text-[11px] text-muted">
              Your data is saved to your workspace automatically.
            </p>
          </div>
        ) : (
        <div key={activeTab} className="min-w-0 rounded-xl border border-line bg-panel/70 p-5 shadow-soft backdrop-blur-xl motion-safe:animate-screen-in sm:p-6">
          {activeTab === "general" && (
            <div className="space-y-6">
              <div className="space-y-1.5">
                <Eyebrow>Workspace</Eyebrow>
                <h3 className="font-display text-lg font-semibold text-ink">Organization</h3>
              </div>
              {generalLoading ? (
                <InlineLoading>Loading settings…</InlineLoading>
              ) : (
                <div className="max-w-md space-y-5">
                  <Field label="Organization Name" htmlFor="settings-org-name">
                    <Input
                      id="settings-org-name"
                      type="text"
                      value={orgName}
                      onChange={(e) => setOrgName(e.target.value)}
                    />
                  </Field>
                  <Field label="Domain" htmlFor="settings-domain">
                    <Input
                      id="settings-domain"
                      type="text"
                      value={domain}
                      onChange={(e) => setDomain(e.target.value)}
                      placeholder="agency.example.com"
                      className="font-mono"
                    />
                  </Field>
                  <div className="space-y-1.5">
                    <p className="text-xs font-medium text-muted">Logo</p>
                    <div className="flex items-center gap-4">
                      <div className="flex h-20 w-20 shrink-0 items-center justify-center rounded-lg border border-dashed border-slate-300 bg-canvas/40 font-mono text-[11px] text-muted">
                        No logo
                      </div>
                      <div className="text-sm text-muted">
                        {/* No upload endpoint exists — render the state, not a button
                            that only fires a toast. */}
                        <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-300 bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-800">
                          <AlertTriangle className="h-3.5 w-3.5 text-amber-600" />
                          Logo upload not available yet
                        </span>
                      </div>
                    </div>
                  </div>
                  <Field label="Default Timezone" htmlFor="settings-timezone">
                    <Select id="settings-timezone" value={timezone} onChange={(e) => setTimezone(e.target.value)}>
                      <option value="UTC">UTC</option>
                      <option value="America/New_York">America/New_York</option>
                      <option value="America/Los_Angeles">America/Los_Angeles</option>
                      <option value="Europe/London">Europe/London</option>
                      <option value="Asia/Singapore">Asia/Singapore</option>
                      <option value="Asia/Tokyo">Asia/Tokyo</option>
                    </Select>
                  </Field>
                  <div className="border-t border-line pt-5">
                    <Button disabled={generalSaving} onClick={() => void handleSaveGeneral()}>
                      {generalSaving ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Save className="h-4 w-4" />
                      )}
                      {saved ? "Saved!" : "Save Changes"}
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}

          {activeTab === "api-keys" && (
            <div className="space-y-6">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="space-y-1.5">
                  <Eyebrow>Integrations</Eyebrow>
                  <h3 className="font-display text-lg font-semibold text-ink">API Keys</h3>
                  <p className="text-sm text-muted">Manage API keys for external integrations.</p>
                </div>
                <Button disabled={keysBusy || keysLoading} onClick={() => void handleCreateApiKey()}>
                  {keysBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                  Create Key
                </Button>
              </div>
              {keysLoading ? (
                <InlineLoading>Loading API keys…</InlineLoading>
              ) : apiKeys.length === 0 ? (
                <div className="rounded-lg border border-dashed border-slate-300 bg-canvas/40 p-8 text-center text-sm text-muted">
                  No API keys created yet. Create one to integrate CampaignForge with your applications.
                </div>
              ) : (
                <ul className="divide-y divide-line rounded-lg border border-line">
                  {apiKeys.map((key) => (
                    <li key={key.id} className="flex items-center justify-between gap-4 px-4 py-3 text-sm">
                      <div className="min-w-0">
                        <p className="font-medium text-ink">{key.label}</p>
                        <p className="mt-0.5 font-mono text-xs text-accent-text">{key.prefix}••••••••</p>
                        <p className="mt-1 font-mono text-[11px] text-muted">Created {key.created}</p>
                      </div>
                      <button
                        type="button"
                        aria-label={`Revoke ${key.label}`}
                        disabled={keysBusy}
                        className="press-scale rounded-md p-2 text-muted transition-colors hover:bg-red-50 hover:text-red-600 disabled:opacity-50"
                        onClick={() => void handleRevokeApiKey(key.id, key.label)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {activeTab === "notifications" && (
            <div className="space-y-6">
              <div className="space-y-1.5">
                <Eyebrow>Alerts</Eyebrow>
                <h3 className="font-display text-lg font-semibold text-ink">Notification Preferences</h3>
              </div>
              <Notice tone="warning" title="Not available yet">
                CampaignForge does not send notifications yet, and these preferences are not
                stored. The types below are listed so you can see what is planned — none of them
                are active today.
              </Notice>
              <div className="space-y-2.5">
                {PLANNED_NOTIFICATION_TYPES.map((pref) => (
                  <div
                    key={pref.id}
                    className="flex items-center justify-between gap-4 rounded-lg border border-dashed border-line bg-canvas/40 p-4"
                  >
                    <div>
                      <p className="font-medium text-muted">{pref.label}</p>
                      <p className="mt-0.5 text-sm text-muted">{pref.desc}</p>
                    </div>
                    <span className="shrink-0 rounded-full border border-line px-2.5 py-1 font-mono text-[11px] text-muted">
                      Planned
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
        )}
      </div>
    </div>
  );
}

function InlineLoading({ children }: { children: React.ReactNode }) {
  return (
    <div role="status" className="flex items-center gap-2 font-mono text-xs text-muted">
      <Loader2 className="h-4 w-4 animate-spin text-accent-text" />
      {children}
    </div>
  );
}
