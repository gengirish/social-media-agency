"use client";

import { useEffect, useState } from "react";
import { Check, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { api, type Plan, type SubscriptionInfo } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Eyebrow } from "@/components/ui/panel";
import { LoadingState } from "@/components/ui/empty-state";

const DISPLAY_PLANS: {
  tier: string;
  name: string;
  price: string;
  subtitle: string;
  features: string[];
  highlight?: boolean;
}[] = [
  {
    tier: "free",
    name: "Free",
    price: "$0",
    subtitle: "Try the workflow",
    features: ["1 client", "5 campaigns / mo", "AI content drafts", "No publishing"],
  },
  {
    tier: "starter",
    name: "Starter",
    price: "$49",
    subtitle: "per month",
    // "Email reports" removed 260817 — no report is ever emailed; reports are
    // generated on request in the dashboard.
    features: ["3 clients", "20 campaigns / mo", "2 platforms", "200 posts / mo"],
  },
  {
    tier: "growth",
    name: "Growth",
    price: "$149",
    subtitle: "per month",
    highlight: true,
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
  {
    tier: "agency",
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
];

export default function PricingPage() {
  const [subscription, setSubscription] = useState<SubscriptionInfo | null>(null);
  const [apiPlans, setApiPlans] = useState<Plan[]>([]);
  const [loading, setLoading] = useState(true);
  const [checkoutTier, setCheckoutTier] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [sub, plans] = await Promise.all([api.getSubscription(), api.getPlans()]);
        if (!cancelled) {
          setSubscription(sub);
          setApiPlans(plans);
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

  function mergeFeatures(tier: string, fallback: string[]) {
    const p = apiPlans.find((x) => x.tier?.toLowerCase() === tier.toLowerCase());
    return p?.features?.length ? p.features : fallback;
  }

  async function handleUpgrade(tier: string) {
    if (tier === "free") return;
    if (currentTier === tier) {
      toast.info("You're already on this plan");
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

  return (
    <div className="mx-auto max-w-6xl space-y-10">
      <div className="flex flex-col items-center space-y-2 text-center">
        <Eyebrow>Billing</Eyebrow>
        <h1 className="font-display text-3xl font-semibold tracking-tight text-ink sm:text-4xl">Simple pricing</h1>
        <p className="max-w-md text-sm text-muted">Upgrade when you need more clients, posts, and platforms</p>
      </div>

      <div className="grid gap-5 pt-2 md:grid-cols-2 xl:grid-cols-4">
        {DISPLAY_PLANS.map((plan, i) => {
          const isCurrent = currentTier === plan.tier;
          const isGrowth = plan.highlight;
          const features = mergeFeatures(plan.tier, plan.features);
          const busy = checkoutTier === plan.tier;

          return (
            <div
              key={plan.tier}
              style={{ animationDelay: `${i * 0.06}s` }}
              className={cn(
                "relative flex flex-col rounded-xl border bg-panel/70 p-6 shadow-soft backdrop-blur-xl transition-[transform,border-color] duration-200 hover:-translate-y-0.5 motion-safe:animate-screen-in",
                isGrowth
                  ? "border-accent/70 shadow-[0_0_0_1px_rgb(var(--c-accent)/0.35),0_18px_48px_rgb(var(--c-accent)/0.14)]"
                  : "border-line hover:border-slate-300"
              )}
            >
              {isGrowth && (
                <span className="absolute -top-3 left-6 rounded-full bg-accent px-3 py-0.5 font-mono text-[10.5px] font-medium tracking-wide text-on-accent shadow-glow">
                  Most Popular
                </span>
              )}
              {isCurrent && (
                <span className="absolute right-4 top-4 inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 font-mono text-[11px] font-medium text-emerald-700">
                  <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-current" />
                  Current Plan
                </span>
              )}

              <h2 className="font-display text-lg font-semibold text-ink">{plan.name}</h2>
              <div className="mt-3 flex items-baseline gap-1.5">
                <span className="font-display text-4xl font-semibold tracking-tight text-ink">{plan.price}</span>
                <span className="font-mono text-xs text-muted">{plan.subtitle}</span>
              </div>

              <ul className="mt-6 flex-1 space-y-2.5 border-t border-line pt-5">
                {features.map((f, i) => (
                  <li key={i} className="flex gap-2.5 text-sm text-ink">
                    <Check className="mt-0.5 h-4 w-4 shrink-0 text-accent-text" />
                    {f}
                  </li>
                ))}
              </ul>

              <Button
                variant={isGrowth ? "primary" : "secondary"}
                disabled={plan.tier === "free" || isCurrent || busy}
                onClick={() => handleUpgrade(plan.tier)}
                className={cn("mt-8 w-full py-2.5", !isGrowth && "text-ink")}
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
    </div>
  );
}
