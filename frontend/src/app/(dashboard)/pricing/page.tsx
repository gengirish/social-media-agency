"use client";

import { useCallback, useEffect, useState } from "react";
import { Check, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import {
  api,
  type Plan,
  type PricingResponse,
  type SubscriptionInfo,
  type WorkspaceProfileId,
  type WorkspaceProfileOption,
} from "@/lib/api";
import { useSession } from "@/lib/session";
import { Button } from "@/components/ui/button";
import { Eyebrow } from "@/components/ui/panel";
import { LoadingState } from "@/components/ui/empty-state";

/*
 * Presentation copy per tier — the name, the headline price and the subtitle.
 * The *set* of tiers shown, their order and which one is recommended all come
 * from the server (`GET /billing/plans`, shaped by the workspace profile), so
 * this map is a lookup, never the list. A tier the server returns that is
 * missing here still renders, from its own PLAN_CONFIG fields.
 *
 * Prices are the real Stripe amounts and do not vary by profile: a profile
 * chooses which of these four plans you are offered, not what they cost.
 */
const TIER_COPY: Record<string, { name: string; price: string; subtitle: string; features: string[] }> = {
  free: {
    name: "Free",
    price: "$0",
    subtitle: "Try the workflow",
    features: ["1 client", "5 campaigns / mo", "AI content drafts", "No publishing"],
  },
  starter: {
    name: "Starter",
    price: "$49",
    subtitle: "per month",
    // "Email reports" removed 260817 — no report is ever emailed; reports are
    // generated on request in the dashboard.
    features: ["3 clients", "20 campaigns / mo", "2 platforms", "200 posts / mo"],
  },
  growth: {
    name: "Growth",
    price: "$149",
    subtitle: "per month",
    // "Team (3 seats)" removed 260817 — no seat limit is defined or enforced
    // anywhere; team members are unlimited on every paid tier today.
    features: [
      "10 clients",
      "Unlimited campaigns",
      "All platforms",
      "Analytics",
      "Team workspaces",
      "1,000 posts / mo",
    ],
  },
  agency: {
    name: "Agency",
    price: "$399",
    subtitle: "per month",
    features: [
      "Unlimited clients",
      "Unlimited campaigns",
      "White-label",
      "Priority support",
      "API access",
      "High post volume",
    ],
  },
};

function titleCase(tier: string) {
  return tier.charAt(0).toUpperCase() + tier.slice(1);
}

/** Dollars from the Stripe amount in cents, for a tier this page has no copy for. */
function priceFrom(plan: Plan) {
  if (plan.amount == null) return "—";
  return `$${Math.round(plan.amount / 100)}`;
}

export default function PricingPage() {
  const { can } = useSession();
  const canManageBilling = can("billing.manage");

  const [subscription, setSubscription] = useState<SubscriptionInfo | null>(null);
  const [pricing, setPricing] = useState<PricingResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [checkoutTier, setCheckoutTier] = useState<string | null>(null);
  const [savingProfile, setSavingProfile] = useState<WorkspaceProfileId | null | "clear">(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [sub, prices] = await Promise.all([api.getSubscription(), api.getPricing()]);
        if (!cancelled) {
          setSubscription(sub);
          setPricing(prices);
        }
      } catch {
        if (!cancelled) toast.error("Could not load billing info");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const currentTier = (subscription?.plan_tier || "free").toLowerCase();

  /*
   * Choosing a profile only reshapes this grid — it starts no subscription and
   * changes no limit, so it saves immediately with no confirm step. Passing the
   * profile that is already set clears it, which is how "show every plan" works.
   */
  const chooseProfile = useCallback(
    async (id: WorkspaceProfileId) => {
      if (!canManageBilling || savingProfile) return;
      const next = pricing?.profile === id ? null : id;
      setSavingProfile(next ?? "clear");
      try {
        const updated = await api.setWorkspaceProfile(next);
        setPricing((prev) => (prev ? { ...prev, profile: updated.profile, plans: updated.plans } : prev));
      } catch (err: unknown) {
        toast.error(err instanceof Error ? err.message : "Could not save that");
      } finally {
        setSavingProfile(null);
      }
    },
    [canManageBilling, pricing?.profile, savingProfile]
  );

  async function handleUpgrade(tier: string) {
    if (tier === "free") return;
    if (currentTier === tier) {
      toast.info("You are already on this plan");
      return;
    }
    setCheckoutTier(tier);
    try {
      const { checkout_url } = await api.createCheckout(tier);
      if (checkout_url) {
        window.location.href = checkout_url;
        return;
      }
      toast.error("No checkout URL returned");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Checkout failed");
    } finally {
      setCheckoutTier(null);
    }
  }

  if (loading) {
    return <LoadingState label="Loading plans" />;
  }

  const plans = pricing?.plans ?? [];
  const profiles = pricing?.profiles ?? [];
  const activeProfile = profiles.find((p) => p.id === pricing?.profile) ?? null;

  return (
    <div className="mx-auto max-w-6xl space-y-10">
      <div className="flex flex-col items-center space-y-2 text-center">
        <Eyebrow>Billing</Eyebrow>
        <h1 className="font-display text-3xl font-semibold tracking-tight text-ink sm:text-4xl">Simple pricing</h1>
        <p className="max-w-md text-sm text-muted">Upgrade when you need more clients, posts, and platforms</p>
      </div>

      {profiles.length > 0 && (
        <ProfilePicker
          profiles={profiles}
          selected={pricing?.profile ?? null}
          saving={savingProfile}
          disabled={!canManageBilling}
          onChoose={chooseProfile}
        />
      )}

      <div
        className={cn(
          "grid gap-5 pt-2 md:grid-cols-2",
          plans.length >= 4 ? "xl:grid-cols-4" : plans.length === 3 ? "xl:grid-cols-3" : "xl:grid-cols-2"
        )}
      >
        {plans.map((plan, i) => {
          const copy = TIER_COPY[plan.tier];
          const isCurrent = currentTier === plan.tier;
          const isRecommended = plan.recommended === true;
          const features = plan.features?.length ? plan.features : (copy?.features ?? []);
          const busy = checkoutTier === plan.tier;

          return (
            <div
              key={plan.tier}
              style={{ animationDelay: `${i * 0.06}s` }}
              className={cn(
                "relative flex flex-col rounded-xl border bg-panel/70 p-6 shadow-soft backdrop-blur-xl transition-[transform,border-color] duration-200 hover:-translate-y-0.5 motion-safe:animate-screen-in",
                isRecommended
                  ? "border-accent/70 shadow-[0_0_0_1px_rgb(var(--c-accent)/0.35),0_18px_48px_rgb(var(--c-accent)/0.14)]"
                  : "border-line hover:border-slate-300"
              )}
            >
              {isRecommended && (
                <span className="absolute -top-3 left-6 rounded-full bg-accent px-3 py-0.5 font-mono text-[10.5px] font-medium tracking-wide text-on-accent shadow-glow">
                  {activeProfile ? "Best for you" : "Most Popular"}
                </span>
              )}
              {isCurrent && (
                <span className="absolute right-4 top-4 inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 font-mono text-[11px] font-medium text-emerald-700">
                  <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-current" />
                  Current Plan
                </span>
              )}

              <h2 className="font-display text-lg font-semibold text-ink">{copy?.name ?? titleCase(plan.tier)}</h2>
              <div className="mt-3 flex items-baseline gap-1.5">
                <span className="font-display text-4xl font-semibold tracking-tight text-ink">
                  {copy?.price ?? priceFrom(plan)}
                </span>
                <span className="font-mono text-xs text-muted">{copy?.subtitle ?? "per month"}</span>
              </div>

              {isRecommended && activeProfile && (
                <p className="mt-3 text-xs leading-relaxed text-accent-text">{activeProfile.reason}</p>
              )}

              <ul className="mt-6 flex-1 space-y-2.5 border-t border-line pt-5">
                {features.map((f, idx) => (
                  <li key={idx} className="flex gap-2.5 text-sm text-ink">
                    <Check className="mt-0.5 h-4 w-4 shrink-0 text-accent-text" />
                    {f}
                  </li>
                ))}
              </ul>

              <Button
                variant={isRecommended ? "primary" : "secondary"}
                disabled={plan.tier === "free" || isCurrent || busy}
                onClick={() => handleUpgrade(plan.tier)}
                className={cn("mt-8 w-full py-2.5", !isRecommended && "text-ink")}
              >
                {busy ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Redirecting…
                  </>
                ) : isCurrent ? (
                  "Current plan"
                ) : plan.tier === "free" ? (
                  "Free forever"
                ) : (
                  "Upgrade"
                )}
              </Button>
            </div>
          );
        })}
      </div>

      {activeProfile && (
        <p className="text-center font-mono text-[11px] text-muted">
          Showing the plans that fit {activeProfile.label.toLowerCase()}.{" "}
          {canManageBilling ? (
            <button type="button" onClick={() => void chooseProfile(activeProfile.id)} className="underline hover:text-ink">
              Show every plan
            </button>
          ) : (
            "Ask a billing admin to change this."
          )}
        </p>
      )}
    </div>
  );
}

/**
 * The "who is this workspace" choice. Selecting one filters and reorders the
 * grid above and marks one plan as the fit — it never changes a price, starts a
 * subscription or grants a capability, and the copy says so.
 *
 * Re-clicking the selected card clears the choice and restores the full grid.
 */
function ProfilePicker({
  profiles,
  selected,
  saving,
  disabled,
  onChoose,
}: {
  profiles: WorkspaceProfileOption[];
  selected: WorkspaceProfileId | null;
  saving: WorkspaceProfileId | null | "clear";
  disabled: boolean;
  onChoose: (id: WorkspaceProfileId) => void;
}) {
  return (
    <section aria-labelledby="profile-picker" className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="profile-picker" className="font-display text-base font-semibold text-ink">
          Which of these are you?
        </h2>
        <p className="font-mono text-[11px] text-muted">Changes which plans are shown — not what they cost.</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        {profiles.map((p) => {
          const isSelected = selected === p.id;
          const busy = saving === p.id || (isSelected && saving === "clear");
          return (
            <button
              key={p.id}
              type="button"
              onClick={() => onChoose(p.id)}
              disabled={disabled || saving !== null}
              aria-pressed={isSelected}
              title={disabled ? "Only a billing admin can change this" : undefined}
              className={cn(
                "relative rounded-xl border p-4 text-left transition-[border-color,transform] duration-200",
                isSelected
                  ? "border-accent bg-accent/5 shadow-[0_0_0_1px_rgb(var(--c-accent)/0.35)]"
                  : "border-line bg-panel/70 hover:border-accent/40",
                disabled ? "cursor-not-allowed opacity-70" : "hover:-translate-y-0.5"
              )}
            >
              <span className="flex items-center gap-2">
                <span className="font-display text-sm font-semibold text-ink">{p.label}</span>
                {busy && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted" aria-hidden />}
                {isSelected && !busy && <Check className="h-3.5 w-3.5 text-accent-text" aria-hidden />}
              </span>
              <span className="mt-1 block text-xs leading-relaxed text-muted">{p.description}</span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
