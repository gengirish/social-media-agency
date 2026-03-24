"use client";

import { useState, type ElementType } from "react";
import { Settings, Key, Bell, Globe, Save, Plus, Trash2 } from "lucide-react";

type Tab = "general" | "platforms" | "api-keys" | "notifications";

type PlatformStatus = "connected" | "not_connected";

interface ApiKeyRow {
  id: string;
  label: string;
  prefix: string;
  created: string;
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
  const [orgName, setOrgName] = useState("My Agency");
  const [saved, setSaved] = useState(false);
  const [apiKeys, setApiKeys] = useState<ApiKeyRow[]>([]);
  const [notificationPrefs, setNotificationPrefs] = useState<
    { id: string; label: string; desc: string; enabled: boolean }[]
  >(() => DEFAULT_NOTIFICATION_PREFS.map((p) => ({ ...p })));

  const tabs: { id: Tab; label: string; icon: ElementType }[] = [
    { id: "general", label: "General", icon: Settings },
    { id: "platforms", label: "Platforms", icon: Globe },
    { id: "api-keys", label: "API Keys", icon: Key },
    { id: "notifications", label: "Notifications", icon: Bell },
  ];

  const handleSave = () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
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
                <label className="mb-1 block text-sm font-medium text-slate-700">Logo</label>
                <div className="flex items-center gap-4">
                  <div className="flex h-20 w-20 shrink-0 items-center justify-center rounded-lg border-2 border-dashed border-slate-200 bg-slate-50 text-xs text-slate-400">
                    No logo
                  </div>
                  <div className="text-sm text-slate-500">
                    <button
                      type="button"
                      className="font-medium text-indigo-600 hover:text-indigo-700"
                      onClick={handleSave}
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
                <select className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500">
                  <option>UTC</option>
                  <option>America/New_York</option>
                  <option>America/Los_Angeles</option>
                  <option>Europe/London</option>
                  <option>Asia/Singapore</option>
                  <option>Asia/Tokyo</option>
                </select>
              </div>
              <button
                type="button"
                onClick={handleSave}
                className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
              >
                <Save className="h-4 w-4" />
                {saved ? "Saved!" : "Save Changes"}
              </button>
            </div>
          </div>
        )}

        {activeTab === "platforms" && (
          <div className="space-y-6">
            <div>
              <h3 className="text-lg font-semibold text-slate-900">Connected Platforms</h3>
              <p className="text-sm text-slate-500">Connect social platforms to enable direct publishing.</p>
            </div>
            <div className="space-y-3">
              {(
                [
                  { name: "X (Twitter)", status: "not_connected" as PlatformStatus },
                  { name: "LinkedIn", status: "not_connected" as PlatformStatus },
                  { name: "Instagram", status: "not_connected" as PlatformStatus },
                  { name: "Facebook", status: "not_connected" as PlatformStatus },
                ] satisfies { name: string; status: PlatformStatus }[]
              ).map((platform) => (
                <div
                  key={platform.name}
                  className="flex items-center justify-between rounded-lg border border-slate-200 p-4"
                >
                  <div className="flex items-center gap-3">
                    <div
                      className={`h-3 w-3 rounded-full ${
                        platform.status === "connected" ? "bg-emerald-500" : "bg-slate-300"
                      }`}
                    />
                    <span className="font-medium text-slate-900">{platform.name}</span>
                  </div>
                  <button
                    type="button"
                    className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-50"
                  >
                    {platform.status === "connected" ? "Disconnect" : "Connect"}
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === "api-keys" && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-lg font-semibold text-slate-900">API Keys</h3>
                <p className="text-sm text-slate-500">Manage API keys for external integrations.</p>
              </div>
              <button
                type="button"
                className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-700"
                onClick={() => {
                  const id = crypto.randomUUID();
                  setApiKeys((prev) => [
                    ...prev,
                    {
                      id,
                      label: `Key ${prev.length + 1}`,
                      prefix: "cf_live_",
                      created: new Date().toISOString().slice(0, 10),
                    },
                  ]);
                }}
              >
                <Plus className="h-4 w-4" /> Create Key
              </button>
            </div>
            {apiKeys.length === 0 ? (
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
                      aria-label={`Remove ${key.label}`}
                      className="rounded-lg p-2 text-slate-400 hover:bg-red-50 hover:text-red-600"
                      onClick={() => setApiKeys((prev) => prev.filter((k) => k.id !== key.id))}
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
