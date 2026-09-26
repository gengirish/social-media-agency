"use client";

import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import { ArrowRight, CheckCircle2, Home, Link2, Loader2, Lock, Search, TrendingUp, UserPlus, Wand2 } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { Eyebrow } from "@/components/ui/panel";
import { clientLabel, useActiveClient } from "@/lib/active-client";
import { setupApi, type OAuthPlatformStatus } from "@/lib/api-setup";
import { cn } from "@/lib/utils";

interface Step {
  id: string;
  label: string;
  body: string;
  cta: string;
  href: string;
  done: boolean;
  icon: ReactNode;
  detail: string | null;
  locked: boolean;
}

const HUB_LINKS = [
  { label: "Posts", sub: "Manage your queue", icon: Home, href: "/content" },
  { label: "Create", sub: "Blog, email, launch copy", icon: Wand2, href: "/create/content" },
  { label: "Insights", sub: "See what is happening", icon: TrendingUp, href: "/analytics" },
];

/**
 * Cadence's Welcome: adaptive onboarding for the active client, or a
 * welcome-back hub once its three setup steps are done. Progress comes from
 * /clients/overview — real counts only.
 */
export default function WelcomePage() {
  const { clients, active, loading, error, refresh } = useActiveClient();

  // Which platforms have app credentials on this server. `null` means "not
  // known yet" — see `publishable` below, which treats that as the old
  // behaviour rather than as "nothing is configured".
  const [oauth, setOauth] = useState<Record<string, OAuthPlatformStatus> | null>(null);
  const activeId = active?.id;
  useEffect(() => {
    if (!activeId) return;
    let cancelled = false;
    setupApi
      .listAccounts(activeId)
      .then((res) => !cancelled && setOauth(res.oauth))
      .catch(() => {
        // Leave it unknown: a failed check must not tell the user publishing is
        // unavailable when it may be perfectly well configured.
      });
    return () => {
      cancelled = true;
    };
  }, [activeId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center gap-2 py-24 font-mono text-xs text-muted">
        <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading your workspace…
      </div>
    );
  }

  if (error) {
    return (
      <div className="mx-auto max-w-2xl px-2 py-14">
        <Eyebrow>Welcome</Eyebrow>
        <h1 className="mt-3 text-[27px] leading-snug text-ink">We couldn&apos;t load your workspace.</h1>
        <button type="button" onClick={() => void refresh()} className="mt-4 font-mono text-xs text-ink underline">
          Try again
        </button>
      </div>
    );
  }

  if (clients.length === 0 || !active) {
    return (
      <div className="mx-auto max-w-2xl animate-screen-in px-2 py-14">
        <Eyebrow>Welcome to CampaignForge</Eyebrow>
        <h1 className="mt-3 text-[27px] leading-snug text-ink">
          Your clients built something worth talking about.
          <br />
          <span className="text-muted">Now let&apos;s get it in front of people.</span>
        </h1>
        <p className="mt-3 max-w-[480px] text-[13.5px] leading-relaxed text-slate-600">
          CampaignForge reads each client&apos;s brand, writes and manages their social presence, and keeps a human — you —
          in control of everything that goes out. Start by adding the first client you manage.
        </p>
        <Link href="/clients?new=1" className={cn(buttonVariants(), "mt-8 w-fit animate-breathe")}>
          <UserPlus className="h-3.5 w-3.5" /> Add your first client <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </div>
    );
  }

  const name = clientLabel(active);
  const profileDone = active.has_brand_profile;
  const accountsDone = active.connected_accounts > 0;
  // CF-01: with no platform app credentials on the server, every Connect button
  // under Setup › Accounts is disabled — so "Connect your first account" is a
  // dead end. `publishable` is false only once we have actually heard back; an
  // unanswered or failed status check keeps the original wording.
  const publishable = oauth === null || Object.values(oauth).some((p) => p.configured);
  const postsDone = active.total_posts > 0;
  const allDone = profileDone && accountsDone && postsDone;
  const isReturning = profileDone || accountsDone || postsDone;
  const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

  const steps: Step[] = [
    {
      id: "profile",
      label: "Set up the brand profile",
      body: `Drop ${name}'s URL — CampaignForge reads the site, pre-fills audience, voice and differentiator, and asks you to confirm. Takes about 2 minutes.`,
      cta: profileDone ? "Edit profile" : "Start here",
      href: "/setup/profile",
      done: profileDone,
      icon: <Search className="h-[15px] w-[15px]" />,
      detail: profileDone ? `Approved — ${name}` : null,
      locked: false,
    },
    {
      id: "accounts",
      label: publishable ? "Connect social accounts" : "Publishing — coming soon",
      body: publishable
        ? "X, LinkedIn and Facebook publish for real once connected. Nothing goes out without your approval."
        : "Publishing isn't switched on for this server yet, so there's nothing to connect. Everything else works — draft, review and approve posts, then copy them out to publish by hand.",
      cta: accountsDone ? "Manage accounts" : publishable ? "Connect accounts" : "See what's available",
      href: "/setup/accounts",
      done: accountsDone,
      icon: <Link2 className="h-[15px] w-[15px]" />,
      detail: accountsDone ? `${plural(active.connected_accounts, "account")} connected` : null,
      locked: !profileDone,
    },
    {
      id: "posts",
      label: "Generate your first post",
      body: "CampaignForge drafts posts for the channels you pick. You review, edit if you want, then approve. It never publishes on its own.",
      cta: postsDone ? "View posts" : "Generate a post",
      href: postsDone ? "/content" : "/campaigns/new",
      done: postsDone,
      icon: <Wand2 className="h-[15px] w-[15px]" />,
      detail: postsDone ? `${plural(active.total_posts, "post")} in queue` : null,
      // Gated on the profile, not on connecting — drafting doesn't need an account.
      locked: !profileDone,
    },
  ];
  const completed = steps.filter((s) => s.done).length;

  if (allDone) {
    return (
      <div className="mx-auto max-w-2xl animate-screen-in px-2 py-14">
        <div className="mb-3 flex items-center gap-2">
          <CheckCircle2 className="h-4 w-4 text-emerald-600" />
          <Eyebrow>{name} is all set up</Eyebrow>
        </div>
        <h1 className="mb-2 text-[27px] leading-snug text-ink">Welcome back.</h1>
        <p className="max-w-[480px] text-[13.5px] leading-relaxed text-slate-600">
          {plural(active.connected_accounts, "channel")} connected · {plural(active.total_posts, "post")} in queue
          {active.pending > 0 ? ` · ${active.pending} waiting for review` : ""}. Jump back in wherever makes sense.
        </p>
        <div className="mt-8 grid gap-3 sm:grid-cols-3">
          {HUB_LINKS.map(({ label, sub, icon: Icon, href }) => (
            <Link
              key={href}
              href={href}
              className="press-scale flex flex-col items-start gap-1.5 rounded-xl border border-line bg-panel/70 px-4 py-4 backdrop-blur-xl"
            >
              <Icon className="h-3.5 w-3.5 text-accent-text" />
              <span className="text-[13.5px] font-medium text-ink">{label}</span>
              <span className="text-[11.5px] text-muted">{sub}</span>
            </Link>
          ))}
        </div>
        <Link href="/content" className={cn(buttonVariants(), "mt-6 w-fit animate-breathe")}>
          <Home className="h-3.5 w-3.5" /> Go to Posts
        </Link>
      </div>
    );
  }

  const nextIndex = steps.findIndex((s) => !s.done);

  return (
    <div className="mx-auto max-w-2xl px-2 py-14">
      <div className="animate-screen-in">
        {isReturning ? (
          <>
            <Eyebrow>Pick up where you left off</Eyebrow>
            <h1 className="mt-3 text-[27px] leading-snug text-ink">
              {completed} of 3 steps done for {name}.
            </h1>
          </>
        ) : (
          <>
            <Eyebrow>Welcome to CampaignForge</Eyebrow>
            <h1 className="mt-3 text-[27px] leading-snug text-ink">
              {name} is on board.
              <br />
              <span className="text-muted">Now let&apos;s get it in front of people.</span>
            </h1>
          </>
        )}
        <p className="mt-3 max-w-[480px] text-[13.5px] leading-relaxed text-slate-600">
          {isReturning
            ? "Three steps to an AI-managed social presence. AI always drafts, you always approve — nothing posts on its own."
            : "CampaignForge reads the brand, writes and manages its social presence, and keeps a human — you — in control of everything that goes out."}
        </p>
      </div>

      {/* Segmented progress bar — progress visible at a glance, not only stated in text. */}
      <div className="mt-6 flex gap-1.5" aria-hidden>
        {steps.map((step, i) => (
          <div key={step.id} className="h-[5px] flex-1 overflow-hidden rounded-full bg-slate-500/15">
            <div
              className={cn(
                "h-full transition-[width] duration-500",
                step.done ? "w-full bg-emerald-500" : i === nextIndex ? "w-0 bg-accent" : "w-0"
              )}
            />
          </div>
        ))}
      </div>

      <ol className="mt-6 space-y-3">
        {steps.map((step, i) => {
          const isNext = i === nextIndex;
          return (
            <li
              key={step.id}
              style={{ animationDelay: `${0.1 + i * 0.1}s` }}
              className={cn(
                "flex animate-screen-in items-start gap-3 rounded-xl border px-4 py-4 backdrop-blur-xl",
                step.done ? "border-emerald-300 bg-emerald-50/40" : isNext ? "border-accent/40 bg-accent/5" : "border-line bg-panel/70",
                step.locked && "opacity-60"
              )}
            >
              <span
                className={cn(
                  "flex h-7 w-7 shrink-0 items-center justify-center rounded-md border",
                  step.done
                    ? "border-emerald-500 bg-emerald-50 text-emerald-600"
                    : isNext
                      ? "border-accent bg-accent/10 text-accent-text"
                      : "border-line text-muted"
                )}
              >
                {step.done ? <CheckCircle2 className="h-3.5 w-3.5" /> : step.icon}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={cn("text-[13.5px] font-medium", step.done ? "text-muted" : "text-ink")}>{step.label}</span>
                  {step.done && step.detail && <span className="font-mono text-[10px] text-emerald-600">{step.detail}</span>}
                </div>
                {!step.done && !step.locked && <p className="mt-1 text-[12.5px] leading-normal text-muted">{step.body}</p>}
                {step.locked && (
                  <p className="mt-1 flex items-center gap-1.5 text-[11.5px] text-muted">
                    <Lock className="h-2.5 w-2.5" /> Unlocks after {steps[0].label.toLowerCase()}
                  </p>
                )}
              </div>
              {!step.locked && (
                <Link
                  href={step.href}
                  className={cn(
                    "flex shrink-0 items-center gap-1 rounded-md border px-3 py-1.5 text-[11.5px] font-medium",
                    !step.done && isNext ? "border-accent bg-accent text-on-accent" : "border-line text-muted"
                  )}
                >
                  {step.cta} {!step.done && <ArrowRight className="h-[11px] w-[11px]" />}
                </Link>
              )}
            </li>
          );
        })}
      </ol>

      <div className="mt-8 flex items-center gap-4">
        {!profileDone ? (
          <Link href="/setup/profile" className={cn(buttonVariants(), "animate-breathe")}>
            Start with the brand profile <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        ) : !accountsDone && publishable ? (
          <Link href="/setup/accounts" className={cn(buttonVariants(), "animate-breathe")}>
            Connect your first account <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        ) : !accountsDone ? (
          /* CF-01: with no provider configured, sending them to Setup › Accounts
             lands on three disabled buttons. Drafting is the real next step. */
          <Link href="/campaigns/new" className={cn(buttonVariants(), "animate-breathe")}>
            Generate your first post <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        ) : (
          <Link href="/campaigns/new" className={cn(buttonVariants(), "animate-breathe")}>
            Generate your first post <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        )}
        {isReturning && (
          <Link href="/content" className="font-mono text-xs text-muted underline">
            Skip to app
          </Link>
        )}
      </div>
    </div>
  );
}
