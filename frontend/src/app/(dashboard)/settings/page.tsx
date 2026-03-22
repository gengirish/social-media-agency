"use client";

import { Settings, Key, CreditCard, Users } from "lucide-react";

export default function SettingsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Settings</h1>
        <p className="mt-1 text-slate-500">Manage your agency configuration</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {[
          { icon: Key, title: "API Keys", desc: "Configure LLM providers, social platform APIs, and integrations" },
          { icon: CreditCard, title: "Billing", desc: "Manage subscription, invoices, and payment methods" },
          { icon: Users, title: "Team", desc: "Invite team members and manage roles" },
          { icon: Settings, title: "General", desc: "Organization name, branding, and preferences" },
        ].map((item) => (
          <div key={item.title} className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm hover:border-indigo-200 cursor-pointer transition-colors">
            <div className="flex items-center gap-3">
              <div className="rounded-lg bg-indigo-50 p-2">
                <item.icon className="h-5 w-5 text-indigo-600" />
              </div>
              <div>
                <h3 className="font-semibold text-slate-900">{item.title}</h3>
                <p className="mt-0.5 text-sm text-slate-500">{item.desc}</p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
