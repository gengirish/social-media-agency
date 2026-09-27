import type { Metadata } from "next";
import Link from "next/link";
import { Sparkles } from "lucide-react";
import { AuthCta } from "@/components/landing/auth-cta";
import { ThemeToggle } from "@/components/theme";

/*
 * Landing page, in the Cadence look the dashboard uses: navy/amber glass over
 * a faint grid, Space Grotesk headlines, Inter body, IBM Plex Mono labels.
 *
 * Server Component by design: everything here is static markup, so the page
 * ships as HTML with no client bundle beyond two islands — the session-aware
 * AuthCta buttons and the theme toggle.
 *
 * Fonts and colors are the app's own: the root layout loads the three
 * families as CSS variables, and every color below reads the theme tokens
 * from tailwind.config.ts (`--c-*`, redefined under `.dark`), so the page
 * follows the same light/dark switch as the dashboard.
 */

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
    <div className="cf">
      <style>{CSS}</style>

      <header className="cf-header">
        <div className="cf-shell cf-header-inner">
          <Link href="#top" className="cf-brand">
            <span className="cf-mark" aria-hidden>
              <Sparkles className="cf-mark-icon" />
            </span>
            <span className="cf-brand-name">CampaignForge AI</span>
          </Link>
          <nav className="cf-nav">
            <a href="#how" className="cf-navlink">How it works</a>
            <a href="#pipeline" className="cf-navlink">Pipeline</a>
            <a href="#features" className="cf-navlink">Features</a>
            <a href="#pricing" className="cf-navlink">Pricing</a>
          </nav>
          <div className="cf-header-cta">
            <ThemeToggle />
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
              <article key={p.name} className={`cf-card cf-plan${p.popular ? " cf-plan-popular" : ""}`}>
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
                <Link
                  href="/sign-up"
                  className={`cf-btn ${p.popular ? "cf-btn-accent" : "cf-btn-outline"} cf-plan-cta`}
                >
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
            <span className="cf-mark cf-mark-sm" aria-hidden>
              <Sparkles className="cf-mark-icon" />
            </span>
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
 * Every color is a theme token (bare "R G B" channels from tailwind.config.ts,
 * swapped under `.dark`), so there is one stylesheet for both themes. The
 * "violet" tone names are kept from the original design; they now paint the
 * Cadence secondary blue.
 */
const CSS = `
.cf {
  --ink: rgb(var(--c-slate-900));
  --ink-2: rgb(var(--c-slate-700));
  --ink-3: rgb(var(--c-slate-600));
  --ink-4: rgb(var(--c-slate-500));
  --bg: rgb(var(--c-canvas));
  --panel: rgb(var(--c-white) / 0.72);
  --panel-solid: rgb(var(--c-white));
  --line: rgb(var(--c-slate-200));
  --line-2: rgb(var(--c-slate-300));
  --accent: rgb(var(--c-accent));
  --accent-text: rgb(var(--c-accent-text));
  --on-accent: rgb(var(--c-on-accent));
  --violet: rgb(var(--c-blue-600));
  --focus: rgb(var(--c-indigo-500));
  --grad: linear-gradient(135deg, #F6D07E 0%, #F2C14E 55%, #E4A72E 100%);
  --shadow: 0 1px 2px rgb(0 0 0 / 0.06), 0 12px 32px rgb(0 0 0 / 0.08);

  background:
    radial-gradient(900px 560px at 8% -6%, rgb(var(--c-accent) / 0.14), transparent 65%),
    radial-gradient(760px 520px at 100% 4%, rgb(94 161 255 / 0.10), transparent 65%),
    linear-gradient(rgb(var(--c-slate-500) / 0.06) 1px, transparent 1px),
    linear-gradient(90deg, rgb(var(--c-slate-500) / 0.06) 1px, transparent 1px),
    var(--bg);
  background-size: auto, auto, 32px 32px, 32px 32px, auto;
  color: var(--ink);
  font-family: var(--font-sans), Inter, system-ui, sans-serif;
  min-height: 100vh;
  overflow-x: hidden;
  -webkit-font-smoothing: antialiased;
}
.dark .cf { --shadow: 0 1px 2px rgb(0 0 0 / 0.24), 0 12px 32px rgb(0 0 0 / 0.28); }
.cf *, .cf *::before, .cf *::after { box-sizing: border-box; }
.cf ::selection { background: var(--accent); color: var(--on-accent); }
.cf a { text-decoration: none; }
.cf a:not(.cf-btn) { color: inherit; }
.cf :focus-visible { outline: 2px solid var(--focus); outline-offset: 3px; border-radius: 6px; }
.cf h1, .cf h2, .cf h3, .cf p, .cf dl, .cf dd, .cf ul { margin: 0; }
.cf ul { list-style: none; padding: 0; }

@keyframes cf-pulse { 0%,100% { opacity:.35 } 50% { opacity:1 } }
@keyframes cf-rise { from { opacity:0; transform:translateY(14px) } to { opacity:1; transform:none } }
@keyframes cf-spin { to { transform: rotate(360deg) } }

.cf-shell { max-width: 1240px; margin: 0 auto; padding-inline: 32px; }

/* Header */
.cf-header {
  position: sticky; top: 0; z-index: 50;
  backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px);
  background: rgb(var(--c-canvas) / 0.75);
  border-bottom: 1px solid var(--line);
  box-shadow: 0 1px 0 rgb(var(--c-accent) / 0.08);
}
.cf-header-inner { display: flex; align-items: center; justify-content: space-between; gap: 24px; padding-block: 14px; }
.cf-brand { display: flex; align-items: center; gap: 10px; min-width: 0; }
.cf-mark {
  width: 30px; height: 30px; border-radius: 7px; flex: none;
  border: 1px solid var(--accent); background: rgb(var(--c-accent) / 0.1); color: var(--accent-text);
  display: grid; place-items: center;
}
.cf-mark-icon { width: 15px; height: 15px; animation: cf-spin 8s linear infinite; }
.cf-mark-sm { width: 26px; height: 26px; }
.cf-mark-sm .cf-mark-icon { width: 13px; height: 13px; }
.cf-brand-name {
  font-family: var(--font-mono), ui-monospace, monospace; font-weight: 500; font-size: 13.5px;
  letter-spacing: 0.14em; text-transform: uppercase; white-space: nowrap;
}
.cf-nav { display: flex; align-items: center; gap: 28px; font-size: 14px; }
.cf-navlink { color: var(--ink-3); transition: color .15s ease; font-size: 14px; }
.cf-navlink:hover { color: var(--ink); }
.cf-header-cta { display: flex; align-items: center; gap: 14px; }
.cf-auth-skeleton {
  display: block; width: 96px; height: 34px; border-radius: 7px;
  background: rgb(var(--c-slate-500) / 0.12); animation: cf-pulse 1.6s ease-in-out infinite;
}

/* Buttons — Cadence GlowButton: mono label, 7px radius, amber gradient primary */
.cf-btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 8px;
  border-radius: 8px; font-family: var(--font-mono), ui-monospace, monospace; font-weight: 500;
  transition: transform .2s cubic-bezier(.16,1,.3,1), box-shadow .2s ease, background .2s ease, border-color .2s ease, color .2s ease;
  padding: 13px 22px; font-size: 14px; white-space: nowrap;
}
.cf-btn:active { transform: scale(0.97); }
.cf-btn-sm { padding: 8px 15px; font-size: 13px; }
.cf-btn-lg { padding: 15px 28px; font-size: 15px; font-weight: 600; }
.cf-btn-solid { background: var(--ink); color: var(--bg); }
.cf-btn-solid:hover { background: var(--grad); color: var(--on-accent); }
.cf-btn-accent {
  background: var(--grad); color: var(--on-accent); font-weight: 600;
  box-shadow: 0 2px 8px rgb(var(--c-accent) / 0.18), inset 0 1px 0 rgb(255 255 255 / 0.2);
}
.cf-btn-accent:hover { transform: translateY(-2px); box-shadow: 0 8px 22px rgb(var(--c-accent) / 0.35), inset 0 1px 0 rgb(255 255 255 / 0.25); }
.cf-btn-ghost { border: 1px solid var(--line-2); color: var(--ink-2); background: var(--panel); }
.cf-btn-ghost:hover { border-color: rgb(var(--c-accent) / 0.5); color: var(--ink); }
.cf-btn-outline { border: 1px solid var(--line-2); color: var(--ink); font-size: 13.5px; padding: 11px 18px; }
.cf-btn-outline:hover { border-color: rgb(var(--c-accent) / 0.55); background: rgb(var(--c-accent) / 0.08); }

/* Hero */
.cf-hero { display: grid; grid-template-columns: 1.05fr 0.95fr; gap: 64px; align-items: center; padding-block: 96px 72px; }
.cf-hero-copy { display: flex; flex-direction: column; align-items: flex-start; gap: 28px; animation: cf-rise .6s cubic-bezier(.22,1,.36,1) both; }
.cf-eyebrow {
  display: inline-flex; align-items: center; gap: 10px;
  padding: 7px 14px 7px 10px; border-radius: 999px;
  border: 1px solid var(--line); background: var(--panel);
  backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
  font-family: var(--font-mono), ui-monospace, monospace; font-size: 11.5px;
  letter-spacing: 0.06em; text-transform: uppercase; color: var(--ink-3);
}
.cf-dot { width: 7px; height: 7px; border-radius: 99px; background: var(--accent); flex: none; box-shadow: 0 0 8px rgb(var(--c-accent) / 0.7); }
.cf-dot-slow { animation: cf-pulse 2.2s ease-in-out infinite; }
.cf-dot-fast { animation: cf-pulse 1.4s ease-in-out infinite; }
.cf-h1 {
  font-family: var(--font-display), sans-serif; font-weight: 600;
  font-size: clamp(46px, 6.2vw, 86px); line-height: 0.96; letter-spacing: -0.035em; text-wrap: balance;
}
/* Deep amber in light mode so the word clears 3:1 on the pale canvas; bright amber in dark. */
.cf-grad {
  background: linear-gradient(100deg, rgb(var(--c-indigo-700)), rgb(var(--c-indigo-500)));
  -webkit-background-clip: text; background-clip: text; color: transparent;
}
.cf-lede { max-width: 520px; font-size: 19px; line-height: 1.55; color: var(--ink-3); text-wrap: pretty; }
.cf-hero-actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.cf-stats { display: flex; gap: 40px; padding-top: 16px; border-top: 1px solid var(--line); width: 100%; max-width: 520px; }
.cf-stat { display: flex; flex-direction: column; gap: 4px; }
.cf-stat-n { font-family: var(--font-display), sans-serif; font-size: 30px; font-weight: 600; letter-spacing: -0.02em; color: var(--accent-text); }
.cf-stat-l { font-family: var(--font-mono), ui-monospace, monospace; font-size: 11.5px; color: var(--ink-4); margin: 0; }

/* Stream panel */
.cf-panel {
  border: 1px solid var(--line); border-radius: 14px;
  background: var(--panel);
  backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px);
  box-shadow: var(--shadow), 0 0 40px rgb(var(--c-accent) / 0.08);
  overflow: hidden;
  animation: cf-rise .6s cubic-bezier(.22,1,.36,1) .1s both;
}
.cf-panel-bar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 13px 18px; border-bottom: 1px solid var(--line);
  font-family: var(--font-mono), ui-monospace, monospace; font-size: 11.5px; color: var(--ink-3);
}
.cf-panel-live { display: flex; align-items: center; gap: 8px; }
.cf-panel-id { color: var(--ink-4); }
.cf-panel-body { padding: 18px; display: flex; flex-direction: column; gap: 9px; font-family: var(--font-mono), ui-monospace, monospace; font-size: 12.5px; }
.cf-line {
  padding: 11px 14px; border-radius: 9px;
  background: rgb(var(--c-canvas) / 0.6); border: 1px solid var(--line);
  color: var(--ink-2); animation: cf-rise .5s ease both;
}
.cf-line-active { background: rgb(var(--c-accent) / 0.1); border-color: rgb(var(--c-accent) / 0.45); color: var(--ink); }
.cf-tone-dim { color: var(--ink-4); }
.cf-tone-violet { color: var(--violet); }
.cf-tone-accent { color: var(--accent-text); }
.cf-caret { animation: cf-pulse 1s steps(2) infinite; color: var(--accent-text); }
.cf-panel-foot { display: flex; align-items: center; justify-content: space-between; padding: 14px 4px 2px; color: var(--ink-4); font-size: 11.5px; }
.cf-pct { color: var(--accent-text); }
.cf-track { height: 4px; border-radius: 99px; background: var(--line); overflow: hidden; }
.cf-fill { width: 62%; height: 100%; border-radius: 99px; background: var(--grad); box-shadow: 0 0 10px rgb(var(--c-accent) / 0.5); }

/* Sections */
.cf-section { padding-block: 80px; }
.cf-section-tight { padding-block: 80px 40px; }
.cf-section-close { padding-block: 60px 100px; }
.cf-section-head { display: flex; align-items: flex-end; justify-content: space-between; gap: 32px; padding-bottom: 40px; }
.cf-section-head-wrap { flex-wrap: wrap; }
.cf-section-head-col { display: flex; flex-direction: column; gap: 12px; }
.cf-section-sub { max-width: 380px; font-size: 16px; line-height: 1.55; color: var(--ink-3); }
.cf-h2 { font-family: var(--font-display), sans-serif; font-size: clamp(32px, 3.6vw, 50px); letter-spacing: -0.03em; font-weight: 600; line-height: 1.04; text-wrap: balance; }
.cf-h2-xl { font-size: clamp(34px, 4.4vw, 58px); letter-spacing: -0.035em; max-width: 760px; }
.cf-h3 { font-family: var(--font-display), sans-serif; font-size: 22px; font-weight: 600; letter-spacing: -0.015em; }
.cf-h3-lg { font-size: 26px; }
.cf-h3-sm { font-size: 19px; }
.cf-copy { font-size: 15px; line-height: 1.6; color: var(--ink-3); }
.cf-copy-sm { font-size: 14px; line-height: 1.55; }
.cf-kicker { font-family: var(--font-mono), ui-monospace, monospace; font-size: 11.5px; letter-spacing: 0.08em; color: var(--accent-text); }
.cf-kicker-violet { color: var(--violet); }
.cf-kicker-muted { color: var(--ink-4); }
.cf-flow { font-family: var(--font-mono), ui-monospace, monospace; font-size: 13px; color: var(--ink-3); margin: 18px 0 40px; overflow-x: auto; }

.cf-grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.cf-grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }
.cf-grid-plans { gap: 16px; align-items: stretch; }

/* Glass card */
.cf-card {
  border-radius: 12px; border: 1px solid var(--line); background: var(--panel);
  backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px);
  box-shadow: var(--shadow);
  display: flex; flex-direction: column;
  transition: transform .2s cubic-bezier(.16,1,.3,1), border-color .2s ease;
}
.cf-card-step { padding: 30px; gap: 12px; }
.cf-card-step:hover, .cf-card-agent:hover { transform: translateY(-2px); border-color: rgb(var(--c-accent) / 0.5); }
.cf-card-lead {
  grid-column: span 2; padding: 28px; gap: 10px; min-height: 170px;
  border-color: rgb(var(--c-accent) / 0.45);
  background:
    radial-gradient(420px 220px at 0% 0%, rgb(var(--c-accent) / 0.16), transparent 70%),
    var(--panel);
}
.cf-card-agent { padding: 26px; gap: 8px; }

/* Features — hairline grid via 1px gap over a rule-coloured backdrop */
.cf-hairline {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px;
  background: var(--line); border: 1px solid var(--line);
  border-radius: 14px; overflow: hidden; box-shadow: var(--shadow);
}
.cf-cell { padding: 34px 30px; background: var(--panel-solid); display: flex; flex-direction: column; gap: 12px; min-height: 196px; transition: background .15s ease; }
.cf-cell:hover { background: rgb(var(--c-slate-50)); }
.cf-chip { width: 10px; height: 10px; border-radius: 3px; }
.cf-chip-accent { background: var(--accent); box-shadow: 0 0 10px rgb(var(--c-accent) / 0.6); }
.cf-chip-violet { background: var(--violet); }
.cf-cell .cf-h3 { margin-top: 6px; }

/* Pricing */
.cf-billing {
  display: flex; align-items: center; gap: 10px; padding: 5px;
  border-radius: 8px; border: 1px solid var(--line); background: var(--panel);
  font-family: var(--font-mono), ui-monospace, monospace; font-size: 11.5px; letter-spacing: 0.05em;
}
.cf-billing-on { padding: 7px 14px; border-radius: 6px; background: var(--accent); color: var(--on-accent); }
.cf-billing-off { padding: 7px 10px; color: var(--ink-3); }
.cf-plan { position: relative; padding: 28px 24px; gap: 18px; }
.cf-plan:hover { border-color: var(--line-2); }
.cf-plan-popular {
  border-color: rgb(var(--c-accent) / 0.7);
  box-shadow: 0 0 0 1px rgb(var(--c-accent) / 0.35), 0 18px 48px rgb(var(--c-accent) / 0.14);
}
.cf-plan-popular:hover { border-color: var(--accent); }
.cf-badge {
  position: absolute; top: -11px; left: 24px; padding: 4px 11px; border-radius: 999px;
  background: var(--accent); color: var(--on-accent);
  font-family: var(--font-mono), ui-monospace, monospace; font-size: 10.5px; letter-spacing: 0.06em;
  box-shadow: 0 6px 18px rgb(var(--c-accent) / 0.35);
}
.cf-plan-head { display: flex; flex-direction: column; gap: 6px; }
.cf-plan-name { font-family: var(--font-display), sans-serif; font-size: 17px; font-weight: 600; }
.cf-plan-blurb { font-size: 13.5px; color: var(--ink-3); }
.cf-plan-price { display: flex; align-items: baseline; gap: 6px; }
.cf-plan-amount { font-family: var(--font-display), sans-serif; font-size: 42px; font-weight: 600; letter-spacing: -0.03em; }
.cf-plan-period { font-family: var(--font-mono), ui-monospace, monospace; font-size: 12px; color: var(--ink-4); }
.cf-plan-feats { display: flex; flex-direction: column; gap: 9px; padding-top: 16px; border-top: 1px solid var(--line); }
.cf-feat { font-size: 14px; color: var(--ink-2); display: flex; gap: 10px; align-items: baseline; }
.cf-feat-dot { width: 5px; height: 5px; border-radius: 99px; background: var(--accent); flex: none; transform: translateY(-2px); }
.cf-plan-cta { margin-top: auto; }

/* Closing CTA */
.cf-cta {
  position: relative; overflow: hidden;
  padding: 72px 48px; border-radius: 16px; border: 1px dashed var(--line-2);
  background:
    radial-gradient(600px 300px at 50% 0%, rgb(var(--c-accent) / 0.16), transparent 70%),
    var(--panel);
  backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px);
  display: flex; flex-direction: column; align-items: center; gap: 22px; text-align: center;
}
.cf-cta-sub { max-width: 520px; font-size: 17px; line-height: 1.55; color: var(--ink-3); }

/* Footer */
.cf-footer { border-top: 1px solid var(--line); background: rgb(var(--c-canvas) / 0.6); }
.cf-footer-inner { display: flex; align-items: center; justify-content: space-between; gap: 24px; flex-wrap: wrap; padding-block: 28px; }
.cf-copyright { font-family: var(--font-mono), ui-monospace, monospace; font-size: 12px; color: var(--ink-4); }
.cf-foot-nav { display: flex; gap: 24px; font-size: 13.5px; flex-wrap: wrap; }

/* Responsive — the design is desktop-first; these are the reflow points. */
@media (max-width: 1080px) {
  .cf-grid-4 { grid-template-columns: repeat(2, 1fr); }
  .cf-card-lead { grid-column: span 2; }
  .cf-hairline { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 900px) {
  .cf-hero { grid-template-columns: 1fr; gap: 48px; padding-block: 56px 48px; }
  .cf-grid-3 { grid-template-columns: 1fr; }
  .cf-nav { display: none; }
  .cf-section-head { flex-direction: column; align-items: flex-start; gap: 16px; }
  .cf-section-sub { max-width: none; }
}
@media (max-width: 640px) {
  .cf-shell { padding-inline: 16px; }
  .cf-header-cta { gap: 8px; }
  .cf-brand-name { font-size: 12px; letter-spacing: 0.1em; }
  .cf-grid-4, .cf-hairline { grid-template-columns: 1fr; }
  .cf-card-lead { grid-column: span 1; }
  .cf-section { padding-block: 56px; }
  .cf-cta { padding: 48px 20px; }
  .cf-stats { gap: 24px; }
  .cf-cell { min-height: 0; }
}
@media (max-width: 420px) {
  .cf-brand-name { display: none; }
}
@media (prefers-reduced-motion: reduce) {
  .cf *, .cf *::before, .cf *::after { animation: none !important; transition: none !important; }
}
`;
