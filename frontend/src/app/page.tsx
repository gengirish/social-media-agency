"use client";

import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import {
  ArrowRight,
  Bot,
  Check,
  Layers,
  LineChart,
  PenLine,
  Radio,
  ShieldCheck,
  Sparkles,
  Users,
  Zap,
} from "lucide-react";

const agents = [
  { name: "Orchestrator", role: "Routes tasks & merges outputs", emoji: "🎯", lane: 0 },
  { name: "Strategy", role: "Positioning & messaging", emoji: "📐", lane: 1 },
  { name: "SEO", role: "Keywords & structure", emoji: "🔎", lane: 1 },
  { name: "Content Writer", role: "Posts & long-form", emoji: "✍️", lane: 2 },
  { name: "Ad Copywriter", role: "Hooks & CTAs", emoji: "📣", lane: 2 },
  { name: "QA / Brand", role: "Voice & compliance", emoji: "✅", lane: 3 },
  { name: "Analytics", role: "Performance & learnings", emoji: "📊", lane: 3 },
] as const;

const plans = [
  {
    name: "Free",
    price: "$0",
    period: "",
    blurb: "Try the full pipeline",
    features: ["1 client", "30 posts / mo", "Community support"],
    cta: "Start free",
    href: "/sign-up",
    featured: false,
  },
  {
    name: "Starter",
    price: "$49",
    period: "/mo",
    blurb: "Solo marketers & founders",
    features: ["3 clients", "200 posts / mo", "Email support", "Brand profiles"],
    cta: "Get Starter",
    href: "/sign-up",
    featured: true,
  },
  {
    name: "Growth",
    price: "$149",
    period: "/mo",
    blurb: "Growing teams",
    features: ["10 clients", "1,000 posts / mo", "Priority support", "Org workspaces"],
    cta: "Get Growth",
    href: "/sign-up",
    featured: false,
  },
  {
    name: "Agency",
    price: "$399",
    period: "/mo",
    blurb: "Scale without headcount",
    features: ["Unlimited clients", "Unlimited posts", "Dedicated success", "Custom SLAs"],
    cta: "Talk to us",
    href: "/sign-up",
    featured: false,
  },
];

const features = [
  {
    title: "Multi-agent orchestration",
    desc: "Seven specialists run in parallel with a single brief—no handoffs, no chaos.",
    icon: Layers,
  },
  {
    title: "Human-in-the-loop review",
    desc: "Approve strategy, copy, and creative before anything ships. You stay in control.",
    icon: Users,
  },
  {
    title: "Real-time streaming dashboard",
    desc: "Watch agents reason and draft live over SSE—like a mission control for campaigns.",
    icon: Radio,
  },
  {
    title: "Multi-platform publishing",
    desc: "Push to X, LinkedIn, and Meta (Facebook & Instagram) from one workflow.",
    icon: Zap,
  },
  {
    title: "Brand learning & consistency",
    desc: "Org-level brand profiles keep tone, guardrails, and QA aligned across clients.",
    icon: ShieldCheck,
  },
  {
    title: "Campaign analytics",
    desc: "Close the loop with performance signals that feed the next brief.",
    icon: LineChart,
  },
];

function NavBar({
  isLoaded,
  isSignedIn,
}: {
  isLoaded: boolean;
  isSignedIn: boolean | undefined;
}) {
  return (
    <header className="fixed inset-x-0 top-0 z-50 border-b border-white/5 bg-slate-950/80 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6">
        <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight text-white">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-violet-500 to-cyan-400 text-lg shadow-lg shadow-violet-500/25">
            CF
          </span>
          <span className="hidden sm:inline">CampaignForge AI</span>
        </Link>
        <nav className="hidden items-center gap-8 text-sm text-slate-300 md:flex">
          <a href="#how-it-works" className="transition hover:text-white">
            How it works
          </a>
          <a href="#demo" className="transition hover:text-white">
            Pipeline
          </a>
          <a href="#features" className="transition hover:text-white">
            Features
          </a>
          <a href="#pricing" className="transition hover:text-white">
            Pricing
          </a>
        </nav>
        <div className="flex items-center gap-3">
          {!isLoaded ? (
            <span className="h-9 w-24 animate-pulse rounded-lg bg-white/10" aria-hidden />
          ) : isSignedIn ? (
            <>
              <Link
                href="/campaigns"
                className="inline-flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-violet-600 to-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-lg shadow-violet-600/30 transition hover:from-violet-500 hover:to-indigo-500"
              >
                Go to Dashboard
                <ArrowRight className="h-4 w-4" />
              </Link>
            </>
          ) : (
            <>
              <Link href="/sign-in" className="text-sm text-slate-300 transition hover:text-white">
                Sign in
              </Link>
              <Link
                href="/sign-up"
                className="inline-flex items-center gap-1.5 rounded-lg bg-white px-4 py-2 text-sm font-semibold text-slate-900 shadow transition hover:bg-slate-100"
              >
                Start free
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}

function HeroSection({ isSignedIn }: { isSignedIn: boolean | undefined }) {
  return (
    <section className="relative overflow-hidden pt-28 pb-20 sm:pt-32 sm:pb-28">
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute -left-1/4 top-0 h-[500px] w-[500px] rounded-full bg-violet-600/20 blur-[120px]" />
        <div className="absolute -right-1/4 bottom-0 h-[400px] w-[400px] rounded-full bg-cyan-500/15 blur-[100px]" />
        <div className="absolute left-1/2 top-1/3 h-px w-[min(80%,800px)] -translate-x-1/2 bg-gradient-to-r from-transparent via-white/10 to-transparent" />
      </div>
      <div className="relative mx-auto max-w-6xl px-4 sm:px-6">
        <div className="mx-auto max-w-3xl text-center">
          <p className="mb-4 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs font-medium uppercase tracking-wider text-cyan-300/90">
            <Sparkles className="h-3.5 w-3.5" />
            Multi-agent marketing OS
          </p>
          <h1 className="text-balance bg-gradient-to-br from-white via-slate-100 to-slate-400 bg-clip-text text-4xl font-bold tracking-tight text-transparent sm:text-5xl lg:text-6xl">
            Replace Your Marketing Agency with 7 AI Agents
          </h1>
          <p className="mt-6 text-pretty text-lg text-slate-400 sm:text-xl">
            One brief. Complete campaign. 5 minutes.{" "}
            <span className="font-semibold text-cyan-400">$49/month.</span>
          </p>
          <div className="mt-10 flex flex-col items-center justify-center gap-4 sm:flex-row">
            {isSignedIn ? (
              <Link
                href="/campaigns"
                className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 px-8 py-4 text-base font-semibold text-white shadow-xl shadow-violet-600/25 transition hover:from-violet-500 hover:to-indigo-500 sm:w-auto"
              >
                Go to Dashboard
                <ArrowRight className="h-5 w-5" />
              </Link>
            ) : (
              <Link
                href="/sign-up"
                className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 px-8 py-4 text-base font-semibold text-white shadow-xl shadow-violet-600/25 transition hover:from-violet-500 hover:to-indigo-500 sm:w-auto"
              >
                Start Free
                <ArrowRight className="h-5 w-5" />
              </Link>
            )}
            <a
              href="#demo"
              className="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-white/15 bg-white/5 px-8 py-4 text-base font-medium text-white backdrop-blur transition hover:border-white/25 hover:bg-white/10 sm:w-auto"
            >
              Watch Demo
              <PenLine className="h-5 w-5 opacity-80" />
            </a>
          </div>
        </div>

        {/* Hero pipeline visual — CSS only */}
        <div className="relative mx-auto mt-16 max-w-4xl">
          <div className="rounded-2xl border border-white/10 bg-slate-900/50 p-6 shadow-2xl backdrop-blur-sm sm:p-8">
            <div className="mb-4 flex items-center justify-between text-xs text-slate-500">
              <span className="flex items-center gap-2">
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
                </span>
                Live agent stream (SSE)
              </span>
              <span className="font-mono text-cyan-400/80">campaign_7a3f…</span>
            </div>
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex flex-1 flex-col gap-2">
                <div className="rounded-lg border border-violet-500/30 bg-violet-500/10 px-4 py-3 text-sm text-violet-100">
                  <span className="font-semibold text-white">Brief</span> — Product launch, devtools audience, 2-week sprint
                </div>
                <div className="flex items-center justify-center text-slate-500">
                  <ArrowRight className="h-4 w-4 rotate-90 sm:rotate-0" />
                </div>
                <div className="rounded-lg border border-cyan-500/40 bg-gradient-to-r from-cyan-500/10 to-violet-500/10 px-4 py-3 text-center text-sm font-medium text-white">
                  Orchestrator
                </div>
              </div>
              <div className="hidden h-24 w-px bg-gradient-to-b from-transparent via-white/20 to-transparent sm:block" />
              <div className="grid flex-1 grid-cols-2 gap-2 sm:gap-3">
                <div className="rounded-lg border border-white/10 bg-slate-800/80 p-3 text-center text-xs text-slate-300 animate-pulse">
                  Strategy ∥
                </div>
                <div className="rounded-lg border border-white/10 bg-slate-800/80 p-3 text-center text-xs text-slate-300 animate-pulse [animation-delay:150ms]">
                  SEO
                </div>
                <div className="rounded-lg border border-white/10 bg-slate-800/80 p-3 text-center text-xs text-slate-300 animate-pulse [animation-delay:300ms]">
                  Content
                </div>
                <div className="rounded-lg border border-white/10 bg-slate-800/80 p-3 text-center text-xs text-slate-300 animate-pulse [animation-delay:450ms]">
                  Ads
                </div>
              </div>
            </div>
            <div className="mt-4 flex flex-wrap items-center justify-center gap-2 border-t border-white/5 pt-4 text-xs text-slate-400">
              <span className="rounded-md bg-amber-500/15 px-2 py-1 text-amber-200">Human review</span>
              <ArrowRight className="h-3 w-3 text-slate-600" />
              <span className="rounded-md bg-emerald-500/15 px-2 py-1 text-emerald-200">QA</span>
              <ArrowRight className="h-3 w-3 text-slate-600" />
              <span className="rounded-md bg-fuchsia-500/15 px-2 py-1 text-fuchsia-200">Publish → X · LinkedIn · Meta</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function HowItWorks() {
  const steps = [
    {
      step: "1",
      title: "Write your brief",
      desc: "Goals, audience, tone, and channels—plain language, no templates required.",
      icon: "📝",
    },
    {
      step: "2",
      title: "Watch AI agents work",
      desc: "Seven specialists stream progress in real time. Parallel lanes, zero bottlenecks.",
      icon: "⚡",
    },
    {
      step: "3",
      title: "Review & publish",
      desc: "You approve the important beats, QA locks brand consistency, then push everywhere.",
      icon: "🚀",
    },
  ];
  return (
    <section id="how-it-works" className="border-t border-white/5 bg-slate-900/40 py-20 sm:py-24">
      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-3xl font-bold tracking-tight text-white sm:text-4xl">How it works</h2>
          <p className="mt-4 text-slate-400">From blank brief to shipped campaign—without the agency overhead.</p>
        </div>
        <div className="mt-14 grid gap-8 md:grid-cols-3">
          {steps.map((s) => (
            <div
              key={s.step}
              className="group relative rounded-2xl border border-white/10 bg-slate-950/60 p-8 transition hover:border-violet-500/30 hover:shadow-lg hover:shadow-violet-500/10"
            >
              <div className="mb-4 text-4xl">{s.icon}</div>
              <div className="mb-2 text-xs font-bold uppercase tracking-widest text-violet-400">Step {s.step}</div>
              <h3 className="text-xl font-semibold text-white">{s.title}</h3>
              <p className="mt-3 text-sm leading-relaxed text-slate-400">{s.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function PipelineSection() {
  return (
    <section id="demo" className="py-20 sm:py-24">
      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-3xl font-bold tracking-tight text-white sm:text-4xl">Seven agents. One pipeline.</h2>
          <p className="mt-4 text-slate-400">
            Brief → Orchestrator → <span className="text-cyan-400">Strategy ∥ SEO</span> →{" "}
            <span className="text-fuchsia-400">Content ∥ Ads</span> → Human review → QA → Publish
          </p>
        </div>

        <div className="mt-14 overflow-x-auto rounded-2xl border border-white/10 bg-slate-900/30 p-6 sm:p-10">
          <div className="min-w-[640px] space-y-6">
            {/* Swimlanes */}
            <div className="flex items-center gap-4 text-xs font-medium uppercase tracking-wider text-slate-500">
              <div className="w-28 shrink-0" />
              <div className="grid flex-1 grid-cols-4 gap-2 text-center">
                <span>Orchestrate</span>
                <span>Research</span>
                <span>Create</span>
                <span>Ship</span>
              </div>
            </div>
            {agents.map((agent) => (
              <div key={agent.name} className="flex items-stretch gap-4">
                <div className="flex w-28 shrink-0 flex-col justify-center rounded-lg border border-white/10 bg-slate-950/80 p-2 text-center">
                  <span className="text-lg">{agent.emoji}</span>
                  <span className="mt-1 text-[10px] font-semibold leading-tight text-white">{agent.name}</span>
                </div>
                <div className="relative grid flex-1 grid-cols-4 gap-2">
                  {[0, 1, 2, 3].map((col) => (
                    <div
                      key={col}
                      className={`relative flex min-h-[52px] items-center rounded-lg border text-xs ${
                        col === agent.lane
                          ? "border-violet-500/50 bg-gradient-to-br from-violet-600/20 to-cyan-600/10 text-slate-200"
                          : "border-white/5 bg-slate-950/40 text-slate-600"
                      }`}
                    >
                      {col === agent.lane ? (
                        <>
                          <Bot className="absolute right-2 top-2 h-3.5 w-3.5 text-violet-400/80" />
                          <p className="px-3 py-2 pr-8 leading-snug">{agent.role}</p>
                        </>
                      ) : null}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function FeaturesSection() {
  return (
    <section id="features" className="border-t border-white/5 bg-slate-900/40 py-20 sm:py-24">
      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-3xl font-bold tracking-tight text-white sm:text-4xl">Built for serious campaigns</h2>
          <p className="mt-4 text-slate-400">Multi-tenant workspaces for orgs, clients, and brand profiles—kept in sync.</p>
        </div>
        <div className="mt-14 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {features.map((f) => (
            <div
              key={f.title}
              className="rounded-2xl border border-white/10 bg-slate-950/50 p-6 transition hover:border-cyan-500/20 hover:bg-slate-950/80"
            >
              <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-violet-600/30 to-cyan-600/20 text-cyan-300">
                <f.icon className="h-5 w-5" />
              </div>
              <h3 className="mt-4 text-lg font-semibold text-white">{f.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-slate-400">{f.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function PricingSection({ isSignedIn }: { isSignedIn: boolean | undefined }) {
  return (
    <section id="pricing" className="py-20 sm:py-24">
      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-3xl font-bold tracking-tight text-white sm:text-4xl">Simple pricing</h2>
          <p className="mt-4 text-slate-400">Start free. Upgrade when you are ready to replace billable hours with agents.</p>
        </div>
        <div className="mt-14 grid gap-6 lg:grid-cols-4">
          {plans.map((plan) => (
            <div
              key={plan.name}
              className={`relative flex flex-col rounded-2xl border p-6 ${
                plan.featured
                  ? "border-violet-500/50 bg-gradient-to-b from-violet-600/15 to-slate-950/80 shadow-xl shadow-violet-600/10"
                  : "border-white/10 bg-slate-950/60"
              }`}
            >
              {plan.featured ? (
                <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-gradient-to-r from-violet-600 to-indigo-600 px-3 py-0.5 text-xs font-semibold text-white">
                  Most popular
                </span>
              ) : null}
              <h3 className="text-lg font-semibold text-white">{plan.name}</h3>
              <div className="mt-4 flex items-baseline gap-1">
                <span className="text-3xl font-bold text-white">{plan.price}</span>
                <span className="text-slate-400">{plan.period}</span>
              </div>
              <p className="mt-2 text-sm text-slate-400">{plan.blurb}</p>
              <ul className="mt-6 flex flex-1 flex-col gap-3 text-sm text-slate-300">
                {plan.features.map((line) => (
                  <li key={line} className="flex gap-2">
                    <Check className="h-4 w-4 shrink-0 text-emerald-400" />
                    {line}
                  </li>
                ))}
              </ul>
              <Link
                href={isSignedIn ? "/campaigns" : plan.href}
                className={`mt-8 block w-full rounded-xl py-3 text-center text-sm font-semibold transition ${
                  plan.featured
                    ? "bg-gradient-to-r from-violet-600 to-indigo-600 text-white hover:from-violet-500 hover:to-indigo-500"
                    : "border border-white/15 bg-white/5 text-white hover:bg-white/10"
                }`}
              >
                {isSignedIn ? "Open dashboard" : plan.cta}
              </Link>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function SocialProof() {
  const placeholders = ["Northline", "Vector Labs", "Pulse CRM", "DraftKit", "Meridian"];
  return (
    <section className="border-t border-white/5 py-16 sm:py-20">
      <div className="mx-auto max-w-6xl px-4 text-center sm:px-6">
        <p className="text-sm font-medium uppercase tracking-wider text-slate-500">Social proof</p>
        <p className="mt-2 text-lg text-slate-300">Trusted by teams who ship campaigns weekly</p>
        <p className="mt-1 text-sm text-slate-500">Placeholder logos — add your customers here</p>
        <div className="mt-10 flex flex-wrap items-center justify-center gap-4 sm:gap-8">
          {placeholders.map((name) => (
            <div
              key={name}
              className="flex h-14 min-w-[120px] items-center justify-center rounded-xl border border-white/10 bg-gradient-to-br from-slate-800/80 to-slate-900/80 px-6 text-xs font-semibold tracking-wide text-slate-400"
            >
              {name}
            </div>
          ))}
        </div>
        <div className="mx-auto mt-12 grid max-w-3xl gap-6 sm:grid-cols-2">
          <blockquote className="rounded-2xl border border-white/10 bg-slate-900/40 p-6 text-left text-sm text-slate-400">
            <p className="text-slate-200">
              “We replaced a $6k/mo retainer with CampaignForge. Same output, five-minute briefs.”
            </p>
            <footer className="mt-4 text-xs text-slate-500">— Placeholder quote, Marketing Lead</footer>
          </blockquote>
          <blockquote className="rounded-2xl border border-white/10 bg-slate-900/40 p-6 text-left text-sm text-slate-400">
            <p className="text-slate-200">“The SSE dashboard feels like mission control. Our clients love the transparency.”</p>
            <footer className="mt-4 text-xs text-slate-500">— Placeholder quote, Agency founder</footer>
          </blockquote>
        </div>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="border-t border-white/10 bg-slate-950 py-12">
      <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-8 px-4 sm:flex-row sm:px-6">
        <div className="text-center sm:text-left">
          <div className="flex items-center justify-center gap-2 font-semibold text-white sm:justify-start">
            <span className="flex h-8 w-8 items-center justify-center rounded-md bg-gradient-to-br from-violet-500 to-cyan-400 text-sm">
              CF
            </span>
            CampaignForge AI
          </div>
          <p className="mt-2 text-sm text-slate-500">© {new Date().getFullYear()} CampaignForge AI. All rights reserved.</p>
        </div>
        <nav className="flex flex-wrap items-center justify-center gap-6 text-sm text-slate-400">
          <a href="#features" className="hover:text-white">
            Features
          </a>
          <a href="#pricing" className="hover:text-white">
            Pricing
          </a>
          <Link href="/sign-in" className="hover:text-white">
            Sign in
          </Link>
          <Link href="/sign-up" className="hover:text-white">
            Sign up
          </Link>
        </nav>
      </div>
    </footer>
  );
}

export default function Home() {
  const { isLoaded, isSignedIn } = useAuth();

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200 antialiased">
      <NavBar isLoaded={isLoaded} isSignedIn={isSignedIn} />
      <main>
        <HeroSection isSignedIn={isSignedIn} />
        <HowItWorks />
        <PipelineSection />
        <FeaturesSection />
        <PricingSection isSignedIn={isSignedIn} />
        <SocialProof />
      </main>
      <Footer />
    </div>
  );
}
