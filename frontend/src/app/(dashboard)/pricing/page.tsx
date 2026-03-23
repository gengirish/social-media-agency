"use client";

import { useEffect, useState } from "react";
import { Check, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { api, type Plan, type SubscriptionInfo } from "@/lib/api";

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
    features: ["3 clients", "20 campaigns / mo", "2 platforms", "Email reports", "200 posts / mo"],
  },
  {
    tier: "growth",
    name: "Growth",
    price: "$149",
    subtitle: "per month",
    highlight: true,
    features: [
      "10 clients",
      "Unlimited campaigns",
      "All platforms",
      "Analytics",
      "Team (3 seats)",
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
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl space-y-10">
      <div className="text-center">
        <h1 className="text-2xl font-bold text-slate-900 sm:text-3xl">Simple pricing</h1>
        <p className="mt-2 text-slate-500">Upgrade when you need more clients, posts, and platforms</p>
      </div>

      <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-4">
        {DISPLAY_PLANS.map((plan) => {
          const isCurrent = currentTier === plan.tier;
          const isGrowth = plan.highlight;
          const features = mergeFeatures(plan.tier, plan.features);
          const busy = checkoutTier === plan.tier;

          return (
            <div
              key={plan.tier}
              className={cn(
                "relative flex flex-col rounded-xl border bg-white p-6 shadow-sm transition-shadow",
                isGrowth ? "border-2 border-indigo-500 shadow-md ring-1 ring-indigo-500/20" : "border-slate-200"
              )}
            >
              {isGrowth && (
                <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-indigo-600 px-3 py-0.5 text-xs font-semibold text-white">
                  Most Popular
                </span>
              )}
              {isCurrent && (
                <span className="absolute right-4 top-4 rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-800">
                  Current Plan
                </span>
              )}

              <h2 className="text-lg font-bold text-slate-900">{plan.name}</h2>
              <div className="mt-2 flex items-baseline gap-1">
                <span className="text-3xl font-bold text-slate-900">{plan.price}</span>
                <span className="text-sm text-slate-500">{plan.subtitle}</span>
              </div>

              <ul className="mt-6 flex-1 space-y-3">
                {features.map((f, i) => (
                  <li key={i} className="flex gap-2 text-sm text-slate-600">
                    <Check className="h-4 w-4 shrink-0 text-indigo-600" />
                    {f}
                  </li>
                ))}
              </ul>

              <button
                type="button"
                disabled={plan.tier === "free" || isCurrent || busy}
                onClick={() => handleUpgrade(plan.tier)}
                className={cn(
                  "mt-8 w-full rounded-lg py-2.5 text-sm font-semibold transition-colors",
                  isGrowth
                    ? "bg-indigo-600 text-white hover:bg-indigo-500 disabled:bg-slate-200 disabled:text-slate-500"
                    : "border border-slate-200 bg-white text-slate-900 hover:bg-slate-50 disabled:opacity-50"
                )}
              >
                {busy ? (
                  <span className="inline-flex items-center justify-center gap-2">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Redirecting…
                  </span>
                ) : isCurrent ? (
                  "Current plan"
                ) : plan.tier === "free" ? (
                  "Free forever"
                ) : (
                  "Upgrade"
                )}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
