"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api, type Client } from "@/lib/api";
import { useActiveClient } from "@/lib/active-client";
import { trackFeature } from "@/lib/analytics";
import { toast } from "sonner";
import { Sparkles, ArrowLeft, ArrowRight, Rocket, Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { canPublish, platformLabel } from "@/lib/platforms";
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

/**
 * Paid ad networks, opt-in and separate from the organic channels above (CF-04).
 *
 * A campaign that picked LinkedIn and X came back with Google and Meta search
 * ads nobody asked for: the Ad Copy agent defaulted to `["google", "meta"]`
 * whatever the brief said. Writing ad copy presumes a media budget, so it is now
 * a deliberate tick here and nothing else turns it on — see
 * `agents/ad_copy.py::selected_ad_platforms`, which is the enforcing end.
 */
const AD_CHANNEL_OPTIONS = [
  { id: "google_ads", label: "Google Ads", emoji: "🔍" },
  { id: "meta_ads", label: "Meta Ads", emoji: "📣" },
  { id: "linkedin_ads", label: "LinkedIn Ads", emoji: "🏢" },
];

/**
 * The budget field's value as a number, or `null` when it is not a number.
 *
 * Blank is 0, not an error: leaving it empty means no budget, which is a normal
 * answer. Rounded to whole cents so the stored figure is a real amount of money
 * rather than a floating-point approximation of one (CF-18).
 *
 * The column stays a USD float — `campaign.budget` is JSONB read in several
 * places, and moving the whole product to integer cents is a wider change than
 * this bug warrants. Rounding here stops the artefacts the field could produce.
 */
/** A yyyy-mm-dd input's value as DD/MM/YYYY, or "" when unset. */
function formatDate(raw: string): string {
  const [y, m, d] = raw.split("-");
  return y && m && d ? `${d}/${m}/${y}` : "";
}

/**
 * The campaign's date range for the Review step (CF-19).
 *
 * Dates and audience were collected and then never shown back, so Review could
 * not be used to check them. Either end can be blank, and `handleLaunch`
 * substitutes today and today+30, so this states what will actually be used
 * rather than leaving a gap. DD/MM/YYYY, per the house convention.
 */
function formatRange(start: string, end: string): string {
  const from = formatDate(start);
  const to = formatDate(end);
  if (from && to) return `${from} – ${to}`;
  if (from) return `${from} – 30 days later`;
  if (to) return `Today – ${to}`;
  return "Today – 30 days later";
}

function parseBudget(raw: string): number | null {
  const trimmed = raw.trim();
  if (!trimmed) return 0;
  const value = Number(trimmed);
  if (!Number.isFinite(value)) return null;
  return Math.round(value * 100) / 100;
}

/* Red ring for a control whose Field is showing an error. */
const invalidClass = "border-red-400 hover:border-red-400 focus:border-red-500 focus:ring-red-500/20";

type ErrorKey =
  | "clientId"
  | "campaignName"
  | "objective"
  | "channels"
  | "endDate"
  | "budgetUsd";

type Errors = Partial<Record<ErrorKey, string>>;

/* In visual order, so the first error found is the first one on screen. */
const FIELD_IDS: { key: ErrorKey; id: string }[] = [
  { key: "clientId", id: "campaign-client" },
  { key: "campaignName", id: "campaign-name" },
  { key: "objective", id: "campaign-objective" },
  { key: "channels", id: "campaign-channels" },
  { key: "endDate", id: "campaign-end" },
  { key: "budgetUsd", id: "campaign-budget" },
];

function NewCampaignForm() {
  const router = useRouter();
  const { activeId } = useActiveClient();
  // CF-14: "Use Template" sends the template id here; nothing used to read it,
  // so the form opened blank.
  const templateId = useSearchParams().get("template");
  const [step, setStep] = useState(1);
  const [clients, setClients] = useState<Client[]>([]);
  const [loading, setLoading] = useState(false);

  const [clientId, setClientId] = useState("");
  const [campaignName, setCampaignName] = useState("");
  const [objective, setObjective] = useState("");
  const [channels, setChannels] = useState<string[]>(["linkedin", "twitter"]);
  // The default pair above is a suggestion, not a choice — a template may
  // replace it, but never a selection the user actually made (CF-14). A ref,
  // not state: it is read once inside the template effect and must not be a
  // dependency of it, or ticking a channel would re-run the prefill.
  const channelsTouched = useRef(false);
  const [templateName, setTemplateName] = useState<string | null>(null);
  const [targetAudience, setTargetAudience] = useState("");
  const [keyMessages, setKeyMessages] = useState("");
  /*
   * CF-18: held as the raw string, not a number.
   *
   * With `useState(0)` the field rendered "0", so typing into it produced
   * "0500". An empty field is empty — it means "no budget set", which is not the
   * same as zero — and only becomes a number on submit.
   */
  const [budgetInput, setBudgetInput] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [additionalContext, setAdditionalContext] = useState("");

  // A step's errors only surface once the user has tried to leave it, then
  // update live so fixing a field clears its message immediately.
  const [attempted, setAttempted] = useState<Record<number, boolean>>({});

  useEffect(() => {
    api.getClients().then((res) => setClients(res.items)).catch(() => {});
  }, []);

  // CF-10: start on the client the top-nav switcher is pointing at. The picker
  // opened empty, so the switcher's choice had to be made a second time here.
  // Only seeds the empty field — it must never overwrite a deliberate pick, and
  // `activeId` changing under a half-filled form should not move the campaign to
  // another client.
  useEffect(() => {
    if (activeId) setClientId((current) => current || activeId);
  }, [activeId]);

  /*
   * CF-14: fill the form from the template behind ?template=<id>.
   *
   * "Use Template" navigated here with the id in the query string and nothing
   * read it, so the form opened blank and the template was decorative. The
   * template's own name, objective, channels and key messages are applied.
   *
   * Only empty fields are filled, so arriving with a half-typed form — or
   * hitting the back button — does not discard what was typed. The objective is
   * the template's `objective_template`, which carries [PRODUCT]/[AUDIENCE]
   * placeholders on purpose: they mark what the user still has to say, and
   * filling them in with a guess is exactly what product rule 4 forbids.
   */
  useEffect(() => {
    if (!templateId) return;
    let cancelled = false;
    api
      .getTemplate(templateId)
      .then((t) => {
        if (cancelled) return;
        setCampaignName((current) => current || t.name);
        setObjective((current) => current || t.objective_template || "");
        if (t.channels?.length && !channelsTouched.current) setChannels(t.channels);
        const messages = (t.content_directives?.key_messages ?? null) as unknown;
        if (Array.isArray(messages) && messages.length) {
          setKeyMessages((current) => current || messages.filter((m) => typeof m === "string").join("\n"));
        }
        setTemplateName(t.name);
      })
      .catch(() => {
        if (!cancelled) toast.error("That template could not be loaded — starting from a blank brief.");
      });
    return () => {
      cancelled = true;
    };
  }, [templateId]);

  function toggleChannel(ch: string) {
    channelsTouched.current = true;
    setChannels((prev) =>
      prev.includes(ch) ? prev.filter((c) => c !== ch) : [...prev, ch]
    );
  }

  // Mirrors the backend's CampaignBrief schema (name >= 3, objective >= 10) so
  // a bad value is caught on the step that owns it, not by a 422 after Launch.
  const stepErrors = useMemo<Record<number, Errors>>(() => {
    const brief: Errors = {};
    if (!clientId) brief.clientId = "Pick the client this campaign is for.";
    const name = campaignName.trim();
    if (!name) brief.campaignName = "Give the campaign a name.";
    else if (name.length < 3) brief.campaignName = "Use at least 3 characters.";
    const goal = objective.trim();
    if (!goal) brief.objective = "Describe what this campaign should achieve.";
    else if (goal.length < 10) brief.objective = "Say a little more — at least 10 characters.";

    const setup: Errors = {};
    // Ad networks alone are not a campaign: the Content agent writes posts for
    // the organic channels, and a brief of "Google Ads only" would produce
    // social posts for an ad network (CF-04).
    if (!channels.some((c) => CHANNEL_OPTIONS.some((o) => o.id === c)))
      setup.channels = "Pick at least one channel.";
    if (startDate && endDate && endDate < startDate)
      setup.endDate = "End date must be on or after the start date.";
    const budget = parseBudget(budgetInput);
    if (budget === null) setup.budgetUsd = "Enter a number, or leave it blank.";
    else if (budget < 0) setup.budgetUsd = "Budget cannot be negative.";

    return { 1: brief, 2: setup, 3: {} };
  }, [clientId, campaignName, objective, channels, startDate, endDate, budgetInput]);

  const errors = attempted[step] ? stepErrors[step] : {};

  function focusFirstError(stepErrs: Errors) {
    const id = FIELD_IDS.find((f) => stepErrs[f.key])?.id;
    if (!id) return;
    const el = document.getElementById(id);
    el?.scrollIntoView({ block: "center", behavior: "smooth" });
    el?.focus({ preventScroll: true });
  }

  function goToStep(target: number) {
    const stepErrs = stepErrors[step];
    // Going back is always allowed; only advancing is gated.
    if (target > step && Object.keys(stepErrs).length > 0) {
      setAttempted((prev) => ({ ...prev, [step]: true }));
      focusFirstError(stepErrs);
      return;
    }
    setStep(target);
    // CF-19: each step is a full card, so advancing left the user part-way down
    // the next one with its first field off-screen.
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function handleLaunch() {
    const blocking = [1, 2].find((s) => Object.keys(stepErrors[s]).length > 0);
    if (blocking) {
      setAttempted((prev) => ({ ...prev, [blocking]: true }));
      setStep(blocking);
      toast.error("Please fix the highlighted fields");
      requestAnimationFrame(() => focusFirstError(stepErrors[blocking]));
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
        budget_usd: parseBudget(budgetInput) ?? 0,
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
          {/* CF-14: say where the prefilled values came from, and that they are
              a starting point rather than something already decided. */}
          {templateName && (
            <p className="rounded-lg border border-line bg-canvas/40 px-3 py-2 text-xs text-muted">
              Started from the <span className="font-medium text-ink">{templateName}</span> template.
              Everything below is editable — the placeholders in square brackets are for you to
              replace.
            </p>
          )}
          <Field label="Client *" htmlFor="campaign-client" error={errors.clientId}>
            <Select
              id="campaign-client"
              value={clientId}
              onChange={(e) => setClientId(e.target.value)}
              aria-invalid={Boolean(errors.clientId)}
              aria-describedby={errors.clientId ? "campaign-client-error" : undefined}
              className={cn(errors.clientId && invalidClass)}
            >
              <option value="">Select a client...</option>
              {clients.map((c) => (
                <option key={c.id} value={c.id}>{c.brand_name} — {c.industry}</option>
              ))}
            </Select>
          </Field>
          <Field label="Campaign Name *" htmlFor="campaign-name" error={errors.campaignName}>
            <Input
              id="campaign-name"
              autoComplete="off"
              value={campaignName}
              onChange={(e) => setCampaignName(e.target.value)}
              placeholder="Q2 Product Launch Campaign"
              aria-invalid={Boolean(errors.campaignName)}
              aria-describedby={errors.campaignName ? "campaign-name-error" : undefined}
              className={cn(errors.campaignName && invalidClass)}
            />
          </Field>
          <Field label="Campaign Objective *" htmlFor="campaign-objective" error={errors.objective}>
            <Textarea
              id="campaign-objective"
              autoComplete="off"
              value={objective}
              onChange={(e) => setObjective(e.target.value)}
              rows={3}
              placeholder="Increase brand awareness and drive sign-ups for our new product launch..."
              aria-invalid={Boolean(errors.objective)}
              aria-describedby={errors.objective ? "campaign-objective-error" : undefined}
              className={cn(errors.objective && invalidClass)}
            />
          </Field>
          <Field label="Target Audience" htmlFor="campaign-audience">
            <Input
              id="campaign-audience"
              autoComplete="off"
              value={targetAudience}
              onChange={(e) => setTargetAudience(e.target.value)}
              placeholder="Tech-savvy professionals, 25-45, interested in productivity tools"
            />
          </Field>
          <Field label="Key Messages (one per line)" htmlFor="campaign-messages">
            <Textarea
              id="campaign-messages"
              autoComplete="off"
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
          <div
            id="campaign-channels"
            tabIndex={-1}
            role="group"
            aria-label="Channels"
            aria-describedby={errors.channels ? "campaign-channels-error" : undefined}
            className="outline-none"
          >
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
            {errors.channels ? (
              <p id="campaign-channels-error" className="mt-2.5 text-xs text-red-600">
                {errors.channels}
              </p>
            ) : (
              <p className="mt-2.5 text-xs text-muted">
                CampaignForge writes and schedules content for every channel above. Channels marked
                &ldquo;draft only&rdquo; cannot be published to automatically yet — you post those
                yourself.
              </p>
            )}
          </div>

          {/* CF-04: paid ads are a separate spend decision, so they are their own
              opt-in. Nothing here is created in an ad account — only copy. */}
          <div role="group" aria-label="Paid ads">
            <p className="mb-2 text-xs font-medium text-muted">Paid ads (optional)</p>
            <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
              {AD_CHANNEL_OPTIONS.map((ch) => {
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
                  </button>
                );
              })}
            </div>
            <p className="mt-2.5 text-xs text-muted">
              Tick one to have the Ad Copy agent draft headline and description variants for it.
              Leave them all off and no ad copy is written. CampaignForge never creates an ad
              campaign or spends a budget — it writes copy for you to use.
            </p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Start Date" htmlFor="campaign-start">
              <Input id="campaign-start" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
            </Field>
            <Field label="End Date" htmlFor="campaign-end" error={errors.endDate}>
              <Input
                id="campaign-end"
                type="date"
                min={startDate || undefined}
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                aria-invalid={Boolean(errors.endDate)}
                aria-describedby={errors.endDate ? "campaign-end-error" : undefined}
                className={cn(errors.endDate && invalidClass)}
              />
            </Field>
          </div>
          <Field label="Budget (USD)" htmlFor="campaign-budget" error={errors.budgetUsd}>
            <Input
              id="campaign-budget"
              type="number"
              min={0}
              step="0.01"
              inputMode="decimal"
              value={budgetInput}
              onChange={(e) => setBudgetInput(e.target.value)}
              placeholder="5000"
              aria-invalid={Boolean(errors.budgetUsd)}
              aria-describedby={errors.budgetUsd ? "campaign-budget-error" : undefined}
              className={cn("font-mono", errors.budgetUsd && invalidClass)}
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
              ["Channels", channels.map(platformLabel).join(", ")],
              ["Dates", formatRange(startDate, endDate)],
              ["Target audience", targetAudience.trim() || "Not set"],
              ["Budget", parseBudget(budgetInput) ? `$${parseBudget(budgetInput)!.toLocaleString()}` : "Not set"],
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
          <Button variant="secondary" onClick={() => goToStep(step - 1)}>
            <ArrowLeft className="h-4 w-4" /> Back
          </Button>
        ) : (
          <div />
        )}

        {step < 3 ? (
          <Button onClick={() => goToStep(step + 1)}>
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

/*
 * `useSearchParams` needs a Suspense boundary or the whole route opts out of
 * static rendering and `next build` complains.
 */
export default function NewCampaignPage() {
  return (
    <Suspense fallback={null}>
      <NewCampaignForm />
    </Suspense>
  );
}
