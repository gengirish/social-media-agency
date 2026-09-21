"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, type Client } from "@/lib/api";
import { trackFeature } from "@/lib/analytics";
import { toast } from "sonner";
import { Sparkles, ArrowLeft, ArrowRight, Rocket, Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { canPublish } from "@/lib/platforms";
import { Button } from "@/components/ui/button";
import { Eyebrow } from "@/components/ui/panel";
import { SectionCard } from "@/components/ui/section-card";
import { Field, Input, Select, Textarea } from "@/components/ui/field";

const STEP_LABELS = ["Brief", "Channels", "Launch"] as const;

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
      trackFeature("campaign-create", { channels });
      toast.success("Campaign launched! Agents are running...");
      router.push(`/campaigns/${campaign.id}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
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
          <Eyebrow>Create · Campaign</Eyebrow>
          <h1 className="font-display text-2xl font-semibold tracking-tight text-ink sm:text-3xl">New Campaign</h1>
          <p className="font-mono text-xs text-muted">
            Step {step} of 3 — {step === 1 ? "Brief" : step === 2 ? "Channels" : "Launch"}
          </p>
        </div>
      </div>

      {/* Progress steps */}
      <ol className="grid grid-cols-3 gap-2" aria-label="Progress">
        {STEP_LABELS.map((label, idx) => {
          const s = idx + 1;
          const done = s < step;
          const current = s === step;
          return (
            <li key={label} aria-current={current ? "step" : undefined} className="space-y-2">
              <div
                className={cn(
                  "h-1 rounded-full transition-colors duration-500",
                  s <= step ? "bg-accent shadow-[0_0_10px_rgb(var(--c-accent)/0.45)]" : "bg-slate-200"
                )}
              />
              <div className={cn("flex items-center gap-1.5 font-mono text-[11px]", s <= step ? "text-ink" : "text-muted")}>
                <span
                  aria-hidden
                  className={cn(
                    "flex h-4 w-4 items-center justify-center rounded-full border text-[9px]",
                    done
                      ? "border-accent bg-accent text-on-accent"
                      : current
                        ? "border-accent text-accent-text"
                        : "border-line"
                  )}
                >
                  {done ? <Check className="h-2.5 w-2.5" /> : s}
                </span>
                {label}
              </div>
            </li>
          );
        })}
      </ol>

      {/* Step 1: Brief */}
      {step === 1 && (
        <SectionCard key="step-1" eyebrow="The brief" bodyClassName="space-y-5">
          <Field label="Client *" htmlFor="campaign-client">
            <Select id="campaign-client" value={clientId} onChange={(e) => setClientId(e.target.value)}>
              <option value="">Select a client...</option>
              {clients.map((c) => (
                <option key={c.id} value={c.id}>{c.brand_name} — {c.industry}</option>
              ))}
            </Select>
          </Field>
          <Field label="Campaign Name *" htmlFor="campaign-name">
            <Input
              id="campaign-name"
              value={campaignName}
              onChange={(e) => setCampaignName(e.target.value)}
              placeholder="Q2 Product Launch Campaign"
            />
          </Field>
          <Field label="Campaign Objective *" htmlFor="campaign-objective">
            <Textarea
              id="campaign-objective"
              value={objective}
              onChange={(e) => setObjective(e.target.value)}
              rows={3}
              placeholder="Increase brand awareness and drive sign-ups for our new product launch..."
            />
          </Field>
          <Field label="Target Audience" htmlFor="campaign-audience">
            <Input
              id="campaign-audience"
              value={targetAudience}
              onChange={(e) => setTargetAudience(e.target.value)}
              placeholder="Tech-savvy professionals, 25-45, interested in productivity tools"
            />
          </Field>
          <Field label="Key Messages (one per line)" htmlFor="campaign-messages">
            <Textarea
              id="campaign-messages"
              value={keyMessages}
              onChange={(e) => setKeyMessages(e.target.value)}
              rows={3}
              placeholder="10x faster than traditional agencies&#10;AI-powered content that converts&#10;Full campaign in minutes"
            />
          </Field>
        </SectionCard>
      )}

      {/* Step 2: Channels & Budget */}
      {step === 2 && (
        <SectionCard key="step-2" eyebrow="Channels & budget" bodyClassName="space-y-5">
          <div>
            <p className="mb-2 text-xs font-medium text-muted">Channels</p>
            <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
              {CHANNEL_OPTIONS.map((ch) => {
                const on = channels.includes(ch.id);
                return (
                  <button
                    key={ch.id}
                    type="button"
                    aria-pressed={on}
                    onClick={() => toggleChannel(ch.id)}
                    className={cn(
                      "press-scale flex items-center gap-2.5 rounded-lg border p-3 text-left text-sm font-medium transition-colors duration-200",
                      on
                        ? "border-accent bg-accent/10 text-ink shadow-[0_0_0_1px_rgb(var(--c-accent)/0.35)]"
                        : "border-line bg-canvas/40 text-muted hover:border-slate-300 hover:text-ink"
                    )}
                  >
                    <span
                      aria-hidden
                      className={cn(
                        "flex h-4 w-4 shrink-0 items-center justify-center rounded border",
                        on ? "border-accent bg-accent text-on-accent" : "border-slate-300"
                      )}
                    >
                      {on && <Check className="h-3 w-3" />}
                    </span>
                    <span aria-hidden className="text-base leading-none">{ch.emoji}</span>
                    {ch.label}
                    {!canPublish(ch.id) && (
                      <span className="ml-auto rounded-full border border-amber-300 bg-amber-50 px-2 py-0.5 font-mono text-[10px] font-medium text-amber-800">
                        draft only
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
            <p className="mt-2.5 text-xs text-muted">
              CampaignForge writes and schedules content for every channel above. Channels marked
              &ldquo;draft only&rdquo; cannot be published to automatically yet — you post those
              yourself.
            </p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Start Date" htmlFor="campaign-start">
              <Input id="campaign-start" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
            </Field>
            <Field label="End Date" htmlFor="campaign-end">
              <Input id="campaign-end" type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
            </Field>
          </div>
          <Field label="Budget (USD)" htmlFor="campaign-budget">
            <Input
              id="campaign-budget"
              type="number"
              value={budgetUsd}
              onChange={(e) => setBudgetUsd(Number(e.target.value))}
              placeholder="5000"
              className="font-mono"
            />
          </Field>
          <Field label="Additional Context" htmlFor="campaign-context">
            <Textarea
              id="campaign-context"
              value={additionalContext}
              onChange={(e) => setAdditionalContext(e.target.value)}
              rows={3}
              placeholder="Any additional instructions, previous campaign learnings, competitor info..."
            />
          </Field>
        </SectionCard>
      )}

      {/* Step 3: Review & Launch */}
      {step === 3 && (
        <SectionCard key="step-3" eyebrow="Review" title="Review Your Campaign" bodyClassName="space-y-5">
          <dl className="divide-y divide-line text-sm">
            {[
              ["Client", clients.find((c) => c.id === clientId)?.brand_name],
              ["Campaign", campaignName],
              ["Channels", channels.join(", ")],
              ["Budget", `$${budgetUsd.toLocaleString()}`],
            ].map(([label, value]) => (
              <div key={label} className="flex justify-between gap-4 py-2.5">
                <dt className="text-muted">{label}</dt>
                <dd className="text-right font-medium text-ink">{value}</dd>
              </div>
            ))}
            <div className="py-2.5">
              <dt className="text-muted">Objective</dt>
              <dd className="mt-1 text-ink">{objective}</dd>
            </div>
          </dl>

          <div className="rounded-lg border border-accent/40 bg-accent/10 p-4 text-sm">
            <div className="flex items-center gap-2 font-semibold text-ink">
              <Sparkles className="h-4 w-4 text-accent-text" />
              7 AI agents will execute this campaign
            </div>
            <p className="mt-1.5 font-mono text-[11px] leading-relaxed text-muted">
              Orchestrator → Strategy ∥ SEO → Content ∥ Ad Copy → QA/Brand Review
            </p>
          </div>
        </SectionCard>
      )}

      {/* Navigation buttons */}
      <div className="flex justify-between">
        {step > 1 ? (
          <Button variant="secondary" onClick={() => setStep(step - 1)}>
            <ArrowLeft className="h-4 w-4" /> Back
          </Button>
        ) : (
          <div />
        )}

        {step < 3 ? (
          <Button onClick={() => setStep(step + 1)}>
            Next <ArrowRight className="h-4 w-4" />
          </Button>
        ) : (
          <Button onClick={handleLaunch} disabled={loading} className="px-6">
            <Rocket className="h-4 w-4" />
            {loading ? "Launching..." : "Launch Campaign"}
          </Button>
        )}
      </div>
    </div>
  );
}
