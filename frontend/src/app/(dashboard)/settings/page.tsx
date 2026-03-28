"use client";

import { useCallback, useEffect, useState, type ElementType } from "react";
import { Settings, Key, Bell, Globe, Save, Plus, Trash2, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";

type Tab = "general" | "platforms" | "api-keys" | "notifications";

interface ApiKeyRow {
  id: string;
  label: string;
  prefix: string;
  created: string;
}

const OAUTH_PLATFORMS: { slug: string; label: string }[] = [
  { slug: "twitter", label: "X (Twitter)" },
  { slug: "linkedin", label: "LinkedIn" },
  { slug: "instagram", label: "Instagram" },
  { slug: "facebook", label: "Facebook" },
];

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

function connectedSlugsFromAccounts(items: unknown[]): Set<string> {
  const s = new Set<string>();
  for (const it of items) {
    const r = it as Record<string, unknown>;
    if (r.connected === false) continue;
    const p = r.platform ?? r.provider ?? r.slug;
    if (typeof p === "string") s.add(p.toLowerCase());
  }
  return s;
}

function isPlatformConnected(slug: string, connected: Set<string>): boolean {
  if (connected.has(slug)) return true;
  if (slug === "twitter" && (connected.has("x") || connected.has("twitter"))) return true;
  return false;
}

const DEFAULT_NOTIFICATION_PREFS = [
  {
    id: "campaign_completed",
    label: "Campaign completed",
    desc: "Get notified when a campaign pipeline finishes",
    enabled: true,
  },
  {
    id: "content_review",
    label: "Content ready for review",
    desc: "Alert when content needs human approval",
    enabled: true,
  },
  {
    id: "publishing_success",
    label: "Publishing success",
    desc: "Confirmation when content is published to platforms",
    enabled: false,
  },
  {
    id: "weekly_digest",
    label: "Weekly performance digest",
    desc: "Summary of campaign performance metrics",
    enabled: false,
  },
] as const;

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<Tab>("general");
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
  const [platformAccounts, setPlatformAccounts] = useState<unknown[]>([]);
  const [platformsLoading, setPlatformsLoading] = useState(false);
  const [oauthBusySlug, setOauthBusySlug] = useState<string | null>(null);
  const [notificationPrefs, setNotificationPrefs] = useState<
    { id: string; label: string; desc: string; enabled: boolean }[]
  >(() => DEFAULT_NOTIFICATION_PREFS.map((p) => ({ ...p })));

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

  const loadPlatforms = useCallback(async () => {
    setPlatformsLoading(true);
    try {
      const res = await api.getPlatformAccounts();
      setPlatformAccounts(res.items ?? []);
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Failed to load platforms");
      setPlatformAccounts([]);
    } finally {
      setPlatformsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadGeneral();
  }, [loadGeneral]);

  useEffect(() => {
    if (activeTab === "api-keys") void loadApiKeys();
  }, [activeTab, loadApiKeys]);

  useEffect(() => {
    if (activeTab === "platforms") void loadPlatforms();
  }, [activeTab, loadPlatforms]);

  const tabs: { id: Tab; label: string; icon: ElementType }[] = [
    { id: "general", label: "General", icon: Settings },
    { id: "platforms", label: "Platforms", icon: Globe },
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

  const handleConnectPlatform = async (slug: string) => {
    setOauthBusySlug(slug);
    try {
      const { authorize_url } = await api.getOAuthUrl(slug);
      if (authorize_url) window.open(authorize_url, "_blank", "noopener,noreferrer");
      else toast.error("No authorize URL returned");
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Could not start OAuth");
    } finally {
      setOauthBusySlug(null);
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

  const toggleNotification = (id: string) => {
    setNotificationPrefs((prev) =>
      prev.map((p) => (p.id === id ? { ...p, enabled: !p.enabled } : p))
    );
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Settings</h1>
        <p className="mt-1 text-slate-500">Manage your agency configuration</p>
      </div>

      <div className="flex gap-1 rounded-lg border border-slate-200 bg-slate-50 p-1">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-colors ${
              activeTab === tab.id
                ? "bg-white text-slate-900 shadow-sm"
                : "text-slate-500 hover:text-slate-700"
            }`}
          >
            <tab.icon className="h-4 w-4" />
            {tab.label}
          </button>
        ))}
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        {activeTab === "general" && (
          <div className="space-y-6">
            <h3 className="text-lg font-semibold text-slate-900">Organization</h3>
            {generalLoading ? (
              <div className="flex items-center gap-2 text-sm text-slate-500">
                <Loader2 className="h-5 w-5 animate-spin text-indigo-600" />
                Loading settings…
              </div>
            ) : (
              <div className="max-w-md space-y-4">
                <div>
                  <label className="mb-1 block text-sm font-medium text-slate-700">Organization Name</label>
                  <input
                    type="text"
                    value={orgName}
                    onChange={(e) => setOrgName(e.target.value)}
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-slate-700">Domain</label>
                  <input
                    type="text"
                    value={domain}
                    onChange={(e) => setDomain(e.target.value)}
                    placeholder="agency.example.com"
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-slate-700">Logo</label>
                  <div className="flex items-center gap-4">
                    <div className="flex h-20 w-20 shrink-0 items-center justify-center rounded-lg border-2 border-dashed border-slate-200 bg-slate-50 text-xs text-slate-400">
                      No logo
                    </div>
                    <div className="text-sm text-slate-500">
                      <button
                        type="button"
                        className="font-medium text-indigo-600 hover:text-indigo-700"
                        onClick={() => toast.message("Logo upload coming soon")}
                      >
                        Upload
                      </button>
                      <span className="text-slate-400"> · </span>
                      PNG or SVG, max 2MB (placeholder)
                    </div>
                  </div>
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-slate-700">Default Timezone</label>
                  <select
                    value={timezone}
                    onChange={(e) => setTimezone(e.target.value)}
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  >
                    <option value="UTC">UTC</option>
                    <option value="America/New_York">America/New_York</option>
                    <option value="America/Los_Angeles">America/Los_Angeles</option>
                    <option value="Europe/London">Europe/London</option>
                    <option value="Asia/Singapore">Asia/Singapore</option>
                    <option value="Asia/Tokyo">Asia/Tokyo</option>
                  </select>
                </div>
                <button
                  type="button"
                  disabled={generalSaving}
                  onClick={() => void handleSaveGeneral()}
                  className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
                >
                  {generalSaving ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Save className="h-4 w-4" />
                  )}
                  {saved ? "Saved!" : "Save Changes"}
                </button>
              </div>
            )}
          </div>
        )}

        {activeTab === "platforms" && (
          <div className="space-y-6">
            <div>
              <h3 className="text-lg font-semibold text-slate-900">Connected Platforms</h3>
              <p className="text-sm text-slate-500">Connect social platforms to enable direct publishing.</p>
            </div>
            {platformsLoading ? (
              <div className="flex items-center gap-2 text-sm text-slate-500">
                <Loader2 className="h-5 w-5 animate-spin text-indigo-600" />
                Loading accounts…
              </div>
            ) : (
              <div className="space-y-3">
                {OAUTH_PLATFORMS.map((platform) => {
                  const connectedSet = connectedSlugsFromAccounts(platformAccounts);
                  const connected = isPlatformConnected(platform.slug, connectedSet);
                  return (
                    <div
                      key={platform.slug}
                      className="flex items-center justify-between rounded-lg border border-slate-200 p-4"
                    >
                      <div className="flex items-center gap-3">
                        <div
                          className={`h-3 w-3 rounded-full ${connected ? "bg-emerald-500" : "bg-slate-300"}`}
                        />
                        <span className="font-medium text-slate-900">{platform.label}</span>
                      </div>
                      <button
                        type="button"
                        disabled={oauthBusySlug === platform.slug}
                        onClick={() => void handleConnectPlatform(platform.slug)}
                        className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-60"
                      >
                        {oauthBusySlug === platform.slug ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : null}
                        {connected ? "Reconnect" : "Connect"}
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {activeTab === "api-keys" && (
          <div className="space-y-6">
            <div className="flex items-center justify-between gap-4">
              <div>
                <h3 className="text-lg font-semibold text-slate-900">API Keys</h3>
                <p className="text-sm text-slate-500">Manage API keys for external integrations.</p>
              </div>
              <button
                type="button"
                disabled={keysBusy || keysLoading}
                className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
                onClick={() => void handleCreateApiKey()}
              >
                {keysBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                Create Key
              </button>
            </div>
            {keysLoading ? (
              <div className="flex items-center gap-2 text-sm text-slate-500">
                <Loader2 className="h-5 w-5 animate-spin text-indigo-600" />
                Loading API keys…
              </div>
            ) : apiKeys.length === 0 ? (
              <div className="rounded-lg border border-slate-200 p-8 text-center text-sm text-slate-500">
                No API keys created yet. Create one to integrate CampaignForge with your applications.
              </div>
            ) : (
              <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200">
                {apiKeys.map((key) => (
                  <li key={key.id} className="flex items-center justify-between gap-4 px-4 py-3 text-sm">
                    <div>
                      <p className="font-medium text-slate-900">{key.label}</p>
                      <p className="mt-0.5 font-mono text-xs text-slate-500">{key.prefix}••••••••</p>
                      <p className="mt-1 text-xs text-slate-400">Created {key.created}</p>
                    </div>
                    <button
                      type="button"
                      aria-label={`Revoke ${key.label}`}
                      disabled={keysBusy}
                      className="rounded-lg p-2 text-slate-400 hover:bg-red-50 hover:text-red-600 disabled:opacity-50"
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
            <h3 className="text-lg font-semibold text-slate-900">Notification Preferences</h3>
            <div className="space-y-4">
              {notificationPrefs.map((pref) => (
                <div
                  key={pref.id}
                  className="flex items-center justify-between rounded-lg border border-slate-200 p-4"
                >
                  <div>
                    <p className="font-medium text-slate-900">{pref.label}</p>
                    <p className="mt-0.5 text-sm text-slate-500">{pref.desc}</p>
                  </div>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={pref.enabled}
                    onClick={() => toggleNotification(pref.id)}
                    className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${
                      pref.enabled ? "bg-indigo-600" : "bg-slate-200"
                    }`}
                  >
                    <span
                      className={`absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${
                        pref.enabled ? "translate-x-5" : ""
                      }`}
                    />
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
