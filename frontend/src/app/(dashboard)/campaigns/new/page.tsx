"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, type Client } from "@/lib/api";
import { toast } from "sonner";
import { Sparkles, ArrowLeft, ArrowRight, Rocket } from "lucide-react";
import { cn } from "@/lib/utils";

const CHANNEL_OPTIONS = [
  { id: "linkedin", label: "LinkedIn", emoji: "💼" },
  { id: "twitter", label: "X / Twitter", emoji: "🐦" },
  { id: "instagram", label: "Instagram", emoji: "📸" },
  { id: "facebook", label: "Facebook", emoji: "📘" },
  { id: "tiktok", label: "TikTok", emoji: "🎵" },
];

export default function NewCampaignPage() {
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [clients, setClients] = useState<Client[]>([]);
  const [loading, setLoading] = useState(false);

  const [clientId, setClientId] = useState("");
  const [campaignName, setCampaignName] = useState("");
  const [objective, setObjective] = useState("");
  const [channels, setChannels] = useState<string[]>(["linkedin", "twitter"]);
  const [targetAudience, setTargetAudience] = useState("");
  const [keyMessages, setKeyMessages] = useState("");
  const [budgetUsd, setBudgetUsd] = useState(0);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [additionalContext, setAdditionalContext] = useState("");

  useEffect(() => {
    api.getClients().then((res) => setClients(res.items)).catch(() => {});
  }, []);

  function toggleChannel(ch: string) {
    setChannels((prev) =>
      prev.includes(ch) ? prev.filter((c) => c !== ch) : [...prev, ch]
    );
  }

  async function handleLaunch() {
    if (!clientId || !campaignName || !objective) {
      toast.error("Please fill in all required fields");
      return;
    }
    setLoading(true);
    try {
      const campaign = await api.createCampaign({
        client_id: clientId,
        campaign_name: campaignName,
        objective,
        channels,
        target_audience: targetAudience,
        key_messages: keyMessages.split("\n").filter(Boolean),
        budget_usd: budgetUsd,
        start_date: startDate || new Date().toISOString().split("T")[0],
        end_date: endDate || new Date(Date.now() + 30 * 86400000).toISOString().split("T")[0],
        additional_context: additionalContext,
      });
      toast.success("Campaign launched! Agents are running...");
      router.push(`/campaigns/${campaign.id}`);
    } catch (err: any) {
      toast.error(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-8">
      <div className="flex items-center gap-4">
        <button onClick={() => router.back()} className="rounded-lg p-2 hover:bg-slate-100">
          <ArrowLeft className="h-5 w-5 text-slate-600" />
        </button>
        <div>
          <h1 className="text-2xl font-bold text-slate-900">New Campaign</h1>
          <p className="text-slate-500">Step {step} of 3 — {step === 1 ? "Brief" : step === 2 ? "Channels" : "Launch"}</p>
        </div>
      </div>

      {/* Progress steps */}
      <div className="flex gap-2">
        {[1, 2, 3].map((s) => (
          <div key={s} className={cn("h-1.5 flex-1 rounded-full", s <= step ? "bg-indigo-600" : "bg-slate-200")} />
        ))}
      </div>

      {/* Step 1: Brief */}
      {step === 1 && (
        <div className="space-y-5 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Client *</label>
            <select
              value={clientId}
              onChange={(e) => setClientId(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-4 py-2.5 text-slate-900 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
            >
              <option value="">Select a client...</option>
              {clients.map((c) => (
                <option key={c.id} value={c.id}>{c.brand_name} — {c.industry}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Campaign Name *</label>
            <input
              value={campaignName}
              onChange={(e) => setCampaignName(e.target.value)}
              placeholder="Q2 Product Launch Campaign"
              className="w-full rounded-lg border border-slate-300 px-4 py-2.5 text-slate-900 placeholder-slate-400 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Campaign Objective *</label>
            <textarea
              value={objective}
              onChange={(e) => setObjective(e.target.value)}
              rows={3}
              placeholder="Increase brand awareness and drive sign-ups for our new product launch..."
              className="w-full rounded-lg border border-slate-300 px-4 py-2.5 text-slate-900 placeholder-slate-400 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 resize-none"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Target Audience</label>
            <input
              value={targetAudience}
              onChange={(e) => setTargetAudience(e.target.value)}
              placeholder="Tech-savvy professionals, 25-45, interested in productivity tools"
              className="w-full rounded-lg border border-slate-300 px-4 py-2.5 text-slate-900 placeholder-slate-400 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Key Messages (one per line)</label>
            <textarea
              value={keyMessages}
              onChange={(e) => setKeyMessages(e.target.value)}
              rows={3}
              placeholder="10x faster than traditional agencies&#10;AI-powered content that converts&#10;Full campaign in minutes"
              className="w-full rounded-lg border border-slate-300 px-4 py-2.5 text-slate-900 placeholder-slate-400 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 resize-none"
            />
          </div>
        </div>
      )}

      {/* Step 2: Channels & Budget */}
      {step === 2 && (
        <div className="space-y-5 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <div>
            <label className="mb-3 block text-sm font-medium text-slate-700">Channels</label>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              {CHANNEL_OPTIONS.map((ch) => (
                <button
                  key={ch.id}
                  onClick={() => toggleChannel(ch.id)}
                  className={cn(
                    "flex items-center gap-2 rounded-xl border-2 p-3 text-sm font-medium transition-all",
                    channels.includes(ch.id)
                      ? "border-indigo-500 bg-indigo-50 text-indigo-700"
                      : "border-slate-200 text-slate-600 hover:border-slate-300"
                  )}
                >
                  <span className="text-lg">{ch.emoji}</span>
                  {ch.label}
                </button>
              ))}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">Start Date</label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="w-full rounded-lg border border-slate-300 px-4 py-2.5 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">End Date</label>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="w-full rounded-lg border border-slate-300 px-4 py-2.5 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
              />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Budget (USD)</label>
            <input
              type="number"
              value={budgetUsd}
              onChange={(e) => setBudgetUsd(Number(e.target.value))}
              placeholder="5000"
              className="w-full rounded-lg border border-slate-300 px-4 py-2.5 text-slate-900 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Additional Context</label>
            <textarea
              value={additionalContext}
              onChange={(e) => setAdditionalContext(e.target.value)}
              rows={3}
              placeholder="Any additional instructions, previous campaign learnings, competitor info..."
              className="w-full rounded-lg border border-slate-300 px-4 py-2.5 text-slate-900 placeholder-slate-400 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 resize-none"
            />
          </div>
        </div>
      )}

      {/* Step 3: Review & Launch */}
      {step === 3 && (
        <div className="space-y-5 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <h3 className="text-lg font-semibold text-slate-900">Review Your Campaign</h3>
          <div className="space-y-3 text-sm">
            <div className="flex justify-between border-b border-slate-100 pb-2">
              <span className="text-slate-500">Client</span>
              <span className="font-medium text-slate-900">{clients.find(c => c.id === clientId)?.brand_name}</span>
            </div>
            <div className="flex justify-between border-b border-slate-100 pb-2">
              <span className="text-slate-500">Campaign</span>
              <span className="font-medium text-slate-900">{campaignName}</span>
            </div>
            <div className="flex justify-between border-b border-slate-100 pb-2">
              <span className="text-slate-500">Channels</span>
              <span className="font-medium text-slate-900">{channels.join(", ")}</span>
            </div>
            <div className="flex justify-between border-b border-slate-100 pb-2">
              <span className="text-slate-500">Budget</span>
              <span className="font-medium text-slate-900">${budgetUsd.toLocaleString()}</span>
            </div>
            <div className="pt-1">
              <span className="text-slate-500">Objective</span>
              <p className="mt-1 text-slate-900">{objective}</p>
            </div>
          </div>

          <div className="rounded-lg bg-indigo-50 p-4 text-sm text-indigo-700">
            <div className="flex items-center gap-2 font-semibold">
              <Sparkles className="h-4 w-4" />
              7 AI agents will execute this campaign
            </div>
            <p className="mt-1 text-indigo-600">
              Orchestrator → Strategy ∥ SEO → Content ∥ Ad Copy → QA/Brand Review
            </p>
          </div>
        </div>
      )}

      {/* Navigation buttons */}
      <div className="flex justify-between">
        {step > 1 ? (
          <button
            onClick={() => setStep(step - 1)}
            className="flex items-center gap-2 rounded-lg border border-slate-300 px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            <ArrowLeft className="h-4 w-4" /> Back
          </button>
        ) : <div />}

        {step < 3 ? (
          <button
            onClick={() => setStep(step + 1)}
            className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500"
          >
            Next <ArrowRight className="h-4 w-4" />
          </button>
        ) : (
          <button
            onClick={handleLaunch}
            disabled={loading}
            className="flex items-center gap-2 rounded-lg bg-indigo-600 px-6 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500 disabled:opacity-50"
          >
            <Rocket className="h-4 w-4" />
            {loading ? "Launching..." : "Launch Campaign"}
          </button>
        )}
      </div>
    </div>
  );
}
