import type { Metadata } from "next";
import Link from "next/link";
import { DM_Sans, JetBrains_Mono, Space_Grotesk } from "next/font/google";
import { AuthCta } from "@/components/landing/auth-cta";

/*
 * Landing page — implements the "CampaignForge Landing" Claude Design file.
 *
 * Server Component by design: everything here is static markup, so the page
 * ships as HTML with no client bundle. Session-dependent buttons live in the
 * AuthCta island.
 *
 * Fonts come from next/font rather than the design's <link> to
 * fonts.googleapis.com — self-hosted, preloaded, and no render-blocking
 * request to a third party. They are scoped to this page via CSS variables on
 * the wrapper, so dashboard routes do not pay for three extra families.
 */

const display = Space_Grotesk({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--cf-display",
  display: "swap",
});

const body = DM_Sans({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--cf-body",
  display: "swap",
});

const mono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--cf-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "CampaignForge AI — Take on more clients without hiring",
  description:
    "Brief in, client-ready campaign out — strategy, SEO, copy and brand QA in one pass, under your logo.",
};

/*
 * Pricing mirrors PLAN_CONFIG in backend/src/agency/services/billing.py.
 * Keep the two in sync by hand — there is no shared source, and a plan shown
 * here that the backend does not enforce is a refund claim waiting to happen.
 *
 * The design also carried an annual/monthly switch. It is rendered in its
 * default (monthly) state only: the backend has no annual Stripe prices, so a
 * working toggle would quote a number nobody can actually be charged.
 */
const PLANS = [
  {
    name: "Free",
    blurb: "Try the full pipeline",
    price: "$0",
    period: "forever",
    cta: "Start free",
    features: ["1 client", "30 posts / mo", "Community support"],
    popular: false,
  },
  {
    name: "Starter",
    blurb: "Freelancers with a few retainers",
    price: "$49",
    period: "/mo",
    cta: "Get Starter",
    features: ["3 clients", "200 posts / mo", "Brand profiles"],
    popular: true,
  },
  {
    name: "Growth",
    blurb: "Small agencies",
    price: "$149",
    period: "/mo",
    cta: "Get Growth",
    features: ["10 clients", "1,000 posts / mo", "Priority support", "Team workspaces"],
    popular: false,
  },
  {
    name: "Agency",
    blurb: "Scale without headcount",
    price: "$399",
    period: "/mo",
    cta: "Talk to us",
    features: ["Unlimited clients", "Unlimited posts", "White-label", "API access"],
    popular: false,
  },
];

const STEPS = [
  {
    step: "STEP 01",
    title: "Write your brief",
    copy: "Goals, audience, tone, and channels — plain language, no templates required.",
  },
  {
    step: "STEP 02",
    title: "Watch agents work",
    copy: "Seven specialists stream progress in real time. Parallel lanes, zero bottlenecks.",
  },
  {
    step: "STEP 03",
    title: "Review & publish",
    copy: "You approve the important beats, QA locks brand consistency, then push everywhere.",
  },
];

const AGENTS = [
  { tag: "02 · RESEARCH", name: "Strategy", copy: "Positioning & messaging", tone: "accent" },
  { tag: "03 · RESEARCH", name: "SEO", copy: "Keywords & structure", tone: "accent" },
  { tag: "04 · CREATE", name: "Content Writer", copy: "Posts & long-form", tone: "muted" },
  { tag: "05 · CREATE", name: "Ad Copywriter", copy: "Hooks & CTAs", tone: "muted" },
  { tag: "06 · SHIP", name: "QA / Brand", copy: "Voice & compliance", tone: "accent" },
  { tag: "07 · SHIP", name: "Analytics", copy: "Performance & learnings", tone: "accent" },
];

const FEATURES = [
  {
    dot: "accent",
    title: "Multi-agent orchestration",
    copy: "Seven specialists run in parallel from a single brief — no handoffs, no chaos.",
  },
  {
    dot: "violet",
    title: "Human-in-the-loop review",
    copy: "Approve strategy, copy, and creative before anything ships. You stay in control.",
  },
  {
    dot: "accent",
    title: "Real-time streaming",
    copy: "Watch agents reason and draft live over SSE — mission control for campaigns.",
  },
  {
    dot: "violet",
    title: "Multi-platform publishing",
    copy: "Publish straight to X, LinkedIn, and Facebook. Instagram and TikTok drafted and scheduled.",
  },
  {
    dot: "accent",
    title: "Brand learning",
    copy: "Org-level brand profiles keep tone, guardrails, and QA aligned across clients.",
  },
  {
    dot: "violet",
    title: "Campaign analytics",
    copy: "Close the loop with performance signals that feed the next brief.",
  },
];

const STREAM_LINES = [
  { label: "brief ›", tone: "dim", text: "product launch · devtools audience · 2-week sprint", delay: "0s" },
  { label: "orchestrator ›", tone: "violet", text: "routing to strategy ∥ seo", delay: ".15s" },
  { label: "strategy ›", tone: "accent", text: "positioning locked — “ship faster, review less”", delay: ".3s" },
  { label: "seo ›", tone: "accent", text: "34 keywords clustered · 6 pillar pages", delay: ".45s" },
];

export default function Home() {
  return (
    <div className={`cf ${display.variable} ${body.variable} ${mono.variable}`}>
      <style>{CSS}</style>

      <header className="cf-header">
        <div className="cf-shell cf-header-inner">
          <Link href="#top" className="cf-brand">
            <span className="cf-mark">CF</span>
            <span className="cf-brand-name">CampaignForge AI</span>
          </Link>
          <nav className="cf-nav">
            <a href="#how" className="cf-navlink">How it works</a>
            <a href="#pipeline" className="cf-navlink">Pipeline</a>
            <a href="#features" className="cf-navlink">Features</a>
            <a href="#pricing" className="cf-navlink">Pricing</a>
          </nav>
          <div className="cf-header-cta">
            <AuthCta variant="header" />
          </div>
        </div>
      </header>

      <main>
        {/* Hero */}
        <section id="top" className="cf-shell cf-hero">
          <div className="cf-hero-copy">
            <span className="cf-eyebrow">
              <span className="cf-dot cf-dot-slow" />
              White-label campaign engine for agencies
            </span>
            <h1 className="cf-h1">
              Take on more clients
              <br />
              without <span className="cf-grad">hiring</span>.
            </h1>
            <p className="cf-lede">
              Brief in, client-ready campaign out — strategy, SEO, copy and brand QA in one pass,
              under your logo.
            </p>
            <div className="cf-hero-actions">
              <AuthCta variant="hero" />
              <a href="#pipeline" className="cf-btn cf-btn-ghost">See the pipeline</a>
            </div>
            <dl className="cf-stats">
              <div className="cf-stat">
                <dt className="cf-stat-n">7</dt>
                <dd className="cf-stat-l">specialist agents</dd>
              </div>
              <div className="cf-stat">
                <dt className="cf-stat-n">1</dt>
                <dd className="cf-stat-l">brief to ship</dd>
              </div>
              <div className="cf-stat">
                <dt className="cf-stat-n">3</dt>
                <dd className="cf-stat-l">publish targets</dd>
              </div>
            </dl>
          </div>

          {/* Illustrative stream panel — sample output, not a live feed. */}
          <div className="cf-panel" aria-hidden>
            <div className="cf-panel-bar">
              <span className="cf-panel-live">
                <span className="cf-dot cf-dot-fast" />
                LIVE AGENT STREAM · SSE
              </span>
              <span className="cf-panel-id">campaign_7a3f</span>
            </div>
            <div className="cf-panel-body">
              {STREAM_LINES.map((l) => (
                <div key={l.label} className="cf-line" style={{ animationDelay: l.delay }}>
                  <span className={`cf-line-tag cf-tone-${l.tone}`}>{l.label}</span> {l.text}
                </div>
              ))}
              <div className="cf-line cf-line-active" style={{ animationDelay: ".6s" }}>
                <span className="cf-line-tag cf-tone-accent">content ›</span> drafting 12 posts
                <span className="cf-caret">_</span>
              </div>
              <div className="cf-panel-foot">
                <span>human review → qa → publish</span>
                <span className="cf-pct">62%</span>
              </div>
              <div className="cf-track">
                <div className="cf-fill" />
              </div>
            </div>
          </div>
        </section>

        {/* How it works */}
        <section id="how" className="cf-shell cf-section">
          <div className="cf-section-head">
            <h2 className="cf-h2">How it works</h2>
            <p className="cf-section-sub">
              From blank brief to client-ready campaign — without adding headcount.
            </p>
          </div>
          <div className="cf-grid-3">
            {STEPS.map((s) => (
              <article key={s.step} className="cf-card cf-card-step">
                <span className="cf-kicker">{s.step}</span>
                <h3 className="cf-h3">{s.title}</h3>
                <p className="cf-copy">{s.copy}</p>
              </article>
            ))}
          </div>
        </section>

        {/* Pipeline */}
        <section id="pipeline" className="cf-shell cf-section">
          <h2 className="cf-h2">Seven agents. One pipeline.</h2>
          <p className="cf-flow">
            brief → orchestrator → strategy ∥ seo → content ∥ ads → human review → qa → publish
          </p>
          <div className="cf-grid-4">
            <article className="cf-card cf-card-lead">
              <span className="cf-kicker cf-kicker-violet">01 · ORCHESTRATE</span>
              <h3 className="cf-h3 cf-h3-lg">Orchestrator</h3>
              <p className="cf-copy">
                Reads the brief, splits the work into parallel lanes, and merges every output back
                into one campaign.
              </p>
            </article>
            {AGENTS.map((a) => (
              <article key={a.name} className="cf-card cf-card-agent">
                <span className={`cf-kicker ${a.tone === "muted" ? "cf-kicker-muted" : ""}`}>
                  {a.tag}
                </span>
                <h3 className="cf-h3 cf-h3-sm">{a.name}</h3>
                <p className="cf-copy cf-copy-sm">{a.copy}</p>
              </article>
            ))}
          </div>
        </section>

        {/* Features */}
        <section id="features" className="cf-shell cf-section">
          <div className="cf-section-head">
            <h2 className="cf-h2">
              Built for serious
              <br />
              campaigns
            </h2>
            <p className="cf-section-sub">
              Multi-tenant workspaces for orgs, clients, and brand profiles — kept in sync.
            </p>
          </div>
          <div className="cf-hairline">
            {FEATURES.map((f) => (
              <article key={f.title} className="cf-cell">
                <span className={`cf-chip cf-chip-${f.dot}`} />
                <h3 className="cf-h3 cf-h3-sm">{f.title}</h3>
                <p className="cf-copy">{f.copy}</p>
              </article>
            ))}
          </div>
        </section>

        {/* Pricing */}
        <section id="pricing" className="cf-shell cf-section cf-section-tight">
          <div className="cf-section-head cf-section-head-wrap">
            <div className="cf-section-head-col">
              <h2 className="cf-h2">Simple pricing</h2>
              <p className="cf-section-sub">
                Start free. Upgrade when you&rsquo;re ready to replace billable hours with agents.
              </p>
            </div>
            <div className="cf-billing">
              <span className="cf-billing-on">MONTHLY</span>
              <span className="cf-billing-off">cancel anytime</span>
            </div>
          </div>
          <div className="cf-grid-4 cf-grid-plans">
            {PLANS.map((p) => (
              <article key={p.name} className="cf-card cf-plan">
                {p.popular && <span className="cf-badge">MOST POPULAR</span>}
                <div className="cf-plan-head">
                  <span className="cf-plan-name">{p.name}</span>
                  <span className="cf-plan-blurb">{p.blurb}</span>
                </div>
                <div className="cf-plan-price">
                  <span className="cf-plan-amount">{p.price}</span>
                  <span className="cf-plan-period">{p.period}</span>
                </div>
                <ul className="cf-plan-feats">
                  {p.features.map((f) => (
                    <li key={f} className="cf-feat">
                      <span className="cf-feat-dot" />
                      {f}
                    </li>
                  ))}
                </ul>
                <Link href="/sign-up" className="cf-btn cf-btn-outline cf-plan-cta">
                  {p.cta}
                </Link>
              </article>
            ))}
          </div>
        </section>

        {/* Closing CTA */}
        <section className="cf-shell cf-section cf-section-close">
          <div className="cf-cta">
            <h2 className="cf-h2 cf-h2-xl">Your entire marketing team. One prompt away.</h2>
            <p className="cf-cta-sub">
              Run your next campaign through the pipeline — free, no card, under your own logo.
            </p>
            <AuthCta variant="final" />
          </div>
        </section>
      </main>

      <footer className="cf-footer">
        <div className="cf-shell cf-footer-inner">
          <div className="cf-brand">
            <span className="cf-mark cf-mark-sm">CF</span>
            <span className="cf-copyright">© 2026 CampaignForge AI</span>
          </div>
          <nav className="cf-foot-nav">
            <a href="#features" className="cf-navlink">Features</a>
            <a href="#pricing" className="cf-navlink">Pricing</a>
            <Link href="/sign-in" className="cf-navlink">Sign in</Link>
            <Link href="/sign-up" className="cf-navlink">Sign up</Link>
          </nav>
        </div>
      </footer>
    </div>
  );
}

/*
 * Scoped under `.cf` so nothing leaks into the dashboard, which is Tailwind.
 * Deliberately single-theme: this is a committed dark marketing surface, so
 * every colour is painted explicitly rather than inherited.
 */
const CSS = `
.cf {
  --ink: oklch(0.97 0.006 275);
  --ink-2: oklch(0.76 0.02 275);
  --ink-3: oklch(0.68 0.02 275);
  --ink-4: oklch(0.58 0.02 275);
  --bg: oklch(0.16 0.012 275);
  --surface: oklch(0.17 0.012 275);
  --surface-2: oklch(0.20 0.014 275);
  --accent: oklch(0.80 0.16 148);
  --accent-hi: oklch(0.88 0.14 148);
  --violet: oklch(0.76 0.16 295);
  --hair: oklch(1 0 0 / 0.09);
  --hair-2: oklch(1 0 0 / 0.16);
  --wash: oklch(1 0 0 / 0.03);

  background:
    radial-gradient(900px 520px at 78% -8%, oklch(0.30 0.09 295 / 0.55), transparent 70%),
    radial-gradient(700px 460px at 8% 12%, oklch(0.28 0.08 148 / 0.35), transparent 70%),
    var(--bg);
  color: var(--ink);
  font-family: var(--cf-body), system-ui, sans-serif;
  min-height: 100vh;
  overflow-x: hidden;
  -webkit-font-smoothing: antialiased;
}
.cf *, .cf *::before, .cf *::after { box-sizing: border-box; }
.cf ::selection { background: var(--accent); color: var(--bg); }
.cf a { text-decoration: none; color: inherit; }
.cf :focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; border-radius: 6px; }
.cf h1, .cf h2, .cf h3, .cf p, .cf dl, .cf dd, .cf ul { margin: 0; }
.cf ul { list-style: none; padding: 0; }

@keyframes cf-pulse { 0%,100% { opacity:.35 } 50% { opacity:1 } }
@keyframes cf-rise { from { opacity:0; transform:translateY(14px) } to { opacity:1; transform:none } }

.cf-shell { max-width: 1240px; margin: 0 auto; padding-inline: 32px; }

/* Header */
.cf-header {
  position: sticky; top: 0; z-index: 50;
  backdrop-filter: blur(18px);
  background: oklch(0.16 0.012 275 / 0.72);
  border-bottom: 1px solid oklch(1 0 0 / 0.07);
}
.cf-header-inner { display: flex; align-items: center; justify-content: space-between; gap: 24px; padding-block: 16px; }
.cf-brand { display: flex; align-items: center; gap: 12px; }
.cf-mark {
  width: 30px; height: 30px; border-radius: 9px; flex: none;
  background: linear-gradient(140deg, var(--accent), oklch(0.72 0.17 295));
  display: grid; place-items: center;
  font-family: var(--cf-display), sans-serif; font-weight: 700; font-size: 13px; color: var(--bg);
}
.cf-mark-sm { width: 26px; height: 26px; border-radius: 8px; font-size: 11px; }
.cf-brand-name { font-family: var(--cf-display), sans-serif; font-weight: 600; font-size: 16px; letter-spacing: -0.01em; }
.cf-nav { display: flex; align-items: center; gap: 28px; font-size: 14px; }
.cf-navlink { color: var(--ink-2); transition: color .15s ease; font-size: 14px; }
.cf-navlink:hover { color: var(--ink); }
.cf-header-cta { display: flex; align-items: center; gap: 14px; }
.cf-auth-skeleton {
  display: block; width: 96px; height: 38px; border-radius: 999px;
  background: oklch(1 0 0 / 0.08); animation: cf-pulse 1.6s ease-in-out infinite;
}

/* Buttons */
.cf-btn {
  display: inline-flex; align-items: center; justify-content: center;
  border-radius: 999px; font-weight: 500; transition: background .15s ease, border-color .15s ease;
  padding: 15px 26px; font-size: 15.5px; white-space: nowrap;
}
.cf-btn-sm { padding: 10px 18px; font-size: 14px; }
.cf-btn-lg { padding: 16px 30px; font-size: 16px; font-weight: 600; }
.cf-btn-solid { background: var(--ink); color: var(--bg); font-weight: 500; }
.cf-btn-solid:hover { background: var(--accent); }
.cf-btn-accent { background: var(--accent); color: var(--bg); font-weight: 600; }
.cf-btn-accent:hover { background: var(--accent-hi); }
.cf-btn-ghost { border: 1px solid var(--hair-2); color: oklch(0.94 0.01 275); }
.cf-btn-ghost:hover { background: oklch(1 0 0 / 0.06); }
.cf-btn-outline { border: 1px solid var(--hair-2); color: oklch(0.95 0.01 275); font-size: 14.5px; padding: 12px 18px; }
.cf-btn-outline:hover { background: oklch(1 0 0 / 0.08); }

/* Hero */
.cf-hero { display: grid; grid-template-columns: 1.05fr 0.95fr; gap: 64px; align-items: center; padding-block: 96px 72px; }
.cf-hero-copy { display: flex; flex-direction: column; align-items: flex-start; gap: 28px; }
.cf-eyebrow {
  display: inline-flex; align-items: center; gap: 10px;
  padding: 7px 14px 7px 10px; border-radius: 999px;
  border: 1px solid oklch(1 0 0 / 0.12); background: oklch(1 0 0 / 0.04);
  font-family: var(--cf-mono), monospace; font-size: 11.5px;
  letter-spacing: 0.06em; text-transform: uppercase; color: oklch(0.82 0.02 275);
}
.cf-dot { width: 7px; height: 7px; border-radius: 99px; background: var(--accent); flex: none; }
.cf-dot-slow { animation: cf-pulse 2.2s ease-in-out infinite; }
.cf-dot-fast { animation: cf-pulse 1.4s ease-in-out infinite; }
.cf-h1 {
  font-family: var(--cf-display), sans-serif; font-weight: 600;
  font-size: clamp(48px, 6.2vw, 88px); line-height: 0.94; letter-spacing: -0.04em; text-wrap: balance;
}
.cf-grad {
  background: linear-gradient(100deg, var(--accent), var(--violet));
  -webkit-background-clip: text; background-clip: text; color: transparent;
}
.cf-lede { max-width: 520px; font-size: 19px; line-height: 1.55; color: var(--ink-2); text-wrap: pretty; }
.cf-hero-actions { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.cf-stats { display: flex; gap: 40px; padding-top: 14px; border-top: 1px solid oklch(1 0 0 / 0.08); width: 100%; max-width: 520px; }
.cf-stat { display: flex; flex-direction: column; gap: 4px; }
.cf-stat-n { font-family: var(--cf-display), sans-serif; font-size: 28px; font-weight: 600; letter-spacing: -0.02em; }
.cf-stat-l { font-size: 13px; color: var(--ink-3); margin: 0; }

/* Stream panel */
.cf-panel {
  border: 1px solid oklch(1 0 0 / 0.10); border-radius: 20px;
  background: oklch(0.19 0.014 275 / 0.85);
  box-shadow: 0 40px 90px -40px oklch(0.05 0.02 275 / 0.9);
  overflow: hidden;
}
.cf-panel-bar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 18px; border-bottom: 1px solid oklch(1 0 0 / 0.08);
  font-family: var(--cf-mono), monospace; font-size: 11.5px; color: var(--ink-3);
}
.cf-panel-live { display: flex; align-items: center; gap: 8px; }
.cf-panel-id { color: var(--ink-4); }
.cf-panel-body { padding: 18px; display: flex; flex-direction: column; gap: 10px; font-family: var(--cf-mono), monospace; font-size: 12.5px; }
.cf-line {
  padding: 12px 14px; border-radius: 12px;
  background: oklch(1 0 0 / 0.04); border: 1px solid oklch(1 0 0 / 0.07);
  color: oklch(0.86 0.01 275); animation: cf-rise .5s ease both;
}
.cf-line-active { background: oklch(0.80 0.16 148 / 0.10); border-color: oklch(0.80 0.16 148 / 0.32); color: oklch(0.92 0.02 148); }
.cf-tone-dim { color: oklch(0.62 0.02 275); }
.cf-tone-violet { color: var(--violet); }
.cf-tone-accent { color: var(--accent); }
.cf-caret { animation: cf-pulse 1s steps(2) infinite; }
.cf-panel-foot { display: flex; align-items: center; justify-content: space-between; padding: 14px 4px 2px; color: var(--ink-4); font-size: 11.5px; }
.cf-pct { color: var(--accent); }
.cf-track { height: 4px; border-radius: 99px; background: oklch(1 0 0 / 0.08); overflow: hidden; }
.cf-fill { width: 62%; height: 100%; background: linear-gradient(90deg, var(--accent), var(--violet)); }

/* Sections */
.cf-section { padding-block: 80px; }
.cf-section-tight { padding-block: 80px 40px; }
.cf-section-close { padding-block: 60px 100px; }
.cf-section-head { display: flex; align-items: flex-end; justify-content: space-between; gap: 32px; padding-bottom: 40px; }
.cf-section-head-wrap { flex-wrap: wrap; }
.cf-section-head-col { display: flex; flex-direction: column; gap: 12px; }
.cf-section-sub { max-width: 380px; font-size: 16px; line-height: 1.55; color: var(--ink-3); }
.cf-h2 { font-family: var(--cf-display), sans-serif; font-size: clamp(32px, 3.6vw, 52px); letter-spacing: -0.03em; font-weight: 600; line-height: 1.02; text-wrap: balance; }
.cf-h2-xl { font-size: clamp(34px, 4.4vw, 60px); letter-spacing: -0.035em; max-width: 760px; }
.cf-h3 { font-family: var(--cf-display), sans-serif; font-size: 24px; font-weight: 600; letter-spacing: -0.02em; }
.cf-h3-lg { font-size: 26px; }
.cf-h3-sm { font-size: 21px; }
.cf-copy { font-size: 15.5px; line-height: 1.6; color: oklch(0.72 0.02 275); }
.cf-copy-sm { font-size: 14.5px; line-height: 1.55; }
.cf-kicker { font-family: var(--cf-mono), monospace; font-size: 11.5px; letter-spacing: 0.08em; color: var(--accent); }
.cf-kicker-violet { color: oklch(0.80 0.10 295); letter-spacing: 0; }
.cf-kicker-muted { color: oklch(0.76 0.02 275); }
.cf-flow { font-family: var(--cf-mono), monospace; font-size: 13px; color: var(--ink-3); margin: 12px 0 40px; overflow-x: auto; }

.cf-grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; }
.cf-grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; }
.cf-grid-plans { gap: 18px; align-items: stretch; }

.cf-card { border-radius: 20px; border: 1px solid var(--hair); background: var(--wash); display: flex; flex-direction: column; }
.cf-card-step { padding: 32px; gap: 14px; transition: border-color .15s ease; }
.cf-card-step:hover { border-color: oklch(0.80 0.16 148 / 0.45); }
.cf-card-lead {
  grid-column: span 2; padding: 28px; gap: 10px; min-height: 170px;
  border-color: oklch(0.76 0.16 295 / 0.35);
  background: linear-gradient(150deg, oklch(0.76 0.16 295 / 0.14), oklch(1 0 0 / 0.02));
}
.cf-card-agent { padding: 28px; gap: 10px; transition: background .15s ease; }
.cf-card-agent:hover { background: oklch(1 0 0 / 0.06); }

/* Features — hairline grid via 1px gap over a rule-coloured backdrop */
.cf-hairline {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px;
  background: var(--hair); border: 1px solid var(--hair);
  border-radius: 22px; overflow: hidden;
}
.cf-cell { padding: 36px 32px; background: var(--surface); display: flex; flex-direction: column; gap: 12px; min-height: 200px; transition: background .15s ease; }
.cf-cell:hover { background: var(--surface-2); }
.cf-chip { width: 10px; height: 10px; border-radius: 3px; }
.cf-chip-accent { background: var(--accent); }
.cf-chip-violet { background: var(--violet); }
.cf-cell .cf-h3 { margin-top: 6px; }

/* Pricing */
.cf-billing {
  display: flex; align-items: center; gap: 10px; padding: 6px;
  border-radius: 999px; border: 1px solid oklch(1 0 0 / 0.12);
  font-family: var(--cf-mono), monospace; font-size: 11.5px; letter-spacing: 0.05em;
}
.cf-billing-on { padding: 8px 16px; border-radius: 999px; background: oklch(1 0 0 / 0.06); color: oklch(0.88 0.01 275); }
.cf-billing-off { padding: 8px 12px; color: oklch(0.62 0.02 275); }
.cf-plan { position: relative; padding: 30px 26px; gap: 18px; border-color: oklch(1 0 0 / 0.10); transition: border-color .15s ease; }
.cf-plan:hover { border-color: oklch(1 0 0 / 0.22); }
.cf-badge {
  position: absolute; top: -11px; left: 26px; padding: 5px 12px; border-radius: 999px;
  background: var(--accent); color: var(--bg);
  font-family: var(--cf-mono), monospace; font-size: 10.5px; letter-spacing: 0.06em;
}
.cf-plan-head { display: flex; flex-direction: column; gap: 6px; }
.cf-plan-name { font-family: var(--cf-display), sans-serif; font-size: 17px; font-weight: 600; }
.cf-plan-blurb { font-size: 13.5px; color: oklch(0.66 0.02 275); }
.cf-plan-price { display: flex; align-items: baseline; gap: 6px; }
.cf-plan-amount { font-family: var(--cf-display), sans-serif; font-size: 42px; font-weight: 600; letter-spacing: -0.03em; }
.cf-plan-period { font-size: 13.5px; color: oklch(0.62 0.02 275); }
.cf-plan-feats { display: flex; flex-direction: column; gap: 9px; padding-top: 4px; border-top: 1px solid oklch(1 0 0 / 0.08); }
.cf-feat { font-size: 14.5px; color: oklch(0.78 0.02 275); display: flex; gap: 10px; align-items: baseline; }
.cf-feat-dot { width: 5px; height: 5px; border-radius: 99px; background: var(--accent); flex: none; }
.cf-plan-cta { margin-top: auto; }

/* Closing CTA */
.cf-cta {
  padding: 72px 48px; border-radius: 28px; border: 1px solid oklch(1 0 0 / 0.10);
  background: linear-gradient(140deg, oklch(0.80 0.16 148 / 0.16), oklch(0.76 0.16 295 / 0.18));
  display: flex; flex-direction: column; align-items: center; gap: 24px; text-align: center;
}
.cf-cta-sub { max-width: 520px; font-size: 17px; line-height: 1.55; color: oklch(0.82 0.02 275); }

/* Footer */
.cf-footer { border-top: 1px solid oklch(1 0 0 / 0.08); }
.cf-footer-inner { display: flex; align-items: center; justify-content: space-between; gap: 24px; flex-wrap: wrap; padding-block: 32px; }
.cf-copyright { font-size: 13.5px; color: oklch(0.62 0.02 275); }
.cf-foot-nav { display: flex; gap: 24px; font-size: 13.5px; }

/* Responsive — the design is desktop-first; these are the reflow points. */
@media (max-width: 1080px) {
  .cf-grid-4 { grid-template-columns: repeat(2, 1fr); }
  .cf-card-lead { grid-column: span 2; }
  .cf-hairline { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 900px) {
  .cf-hero { grid-template-columns: 1fr; gap: 48px; padding-block: 64px 56px; }
  .cf-grid-3 { grid-template-columns: 1fr; }
  .cf-nav { display: none; }
  .cf-section-head { flex-direction: column; align-items: flex-start; gap: 16px; }
  .cf-section-sub { max-width: none; }
}
@media (max-width: 640px) {
  .cf-shell { padding-inline: 20px; }
  .cf-grid-4, .cf-hairline { grid-template-columns: 1fr; }
  .cf-card-lead { grid-column: span 1; }
  .cf-section { padding-block: 56px; }
  .cf-cta { padding: 48px 24px; }
  .cf-stats { gap: 24px; }
  .cf-cell { min-height: 0; }
}
@media (prefers-reduced-motion: reduce) {
  .cf *, .cf *::before, .cf *::after { animation: none !important; transition: none !important; }
}
`;
