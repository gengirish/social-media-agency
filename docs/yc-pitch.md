# CampaignForge AI — YC Application (S2027)

> **Take on more clients without hiring.**
> Brief in, client-ready campaign out — under the agency's own logo.

---

## 1. Company Description

CampaignForge is an AI-native marketing platform where 7 specialized agents collaborate in a visible LangGraph pipeline. Users type one brief, watch agents think and generate in real time via SSE streaming, review output at a human-in-the-loop checkpoint, then publish across platforms — all in under 5 minutes.

**Agents:** Strategist, SEO Researcher, Content Writer, Ad Copywriter, Human Review, QA/Brand, Analytics

**Live:** [campaignforge.intelliforge.tech](https://campaignforge.intelliforge.tech) | **API:** [campaignforge-api.fly.dev](https://campaignforge-api.fly.dev)

---

## 2. The Problem

| Pain Point | Reality |
|-----------|---------|
| Agency cost | SMBs spend $3,000–10,000/month on marketing agencies |
| DIY time sink | Founders spend 15–20 hours/week doing marketing manually |
| Fragmented AI tools | Jasper does copy. Uplane does ads. Rankai does SEO. None does the full job |
| Black-box outputs | Existing tools generate isolated content with no strategy, QC, or brand consistency |
| No quality gate | AI-generated content ships without review — brand risk |

**Bottom line:** No tool replaces the *entire agency workflow*. They replace one person on the team.

---

## 3. The Solution

CampaignForge mirrors how real agencies work — specialized roles, parallel execution, quality gates — at **1/50th the cost** and **100x the speed**.

| Differentiator | What It Means |
|---------------|--------------|
| **Full-stack pipeline** | Strategy → SEO → Content → Ads → QA (not just one function) |
| **Transparent agents** | Users see what each agent thinks in real time (not a black box) |
| **Human-in-the-loop** | Built-in review checkpoint before anything ships |
| **Brand voice enforcement** | Deep brand profiles that get smarter with every campaign |
| **Multi-platform publishing** | Direct to X, LinkedIn, Facebook, Instagram |
| **Autonomous operator** | Set a goal, agents plan and execute weekly cycles |

---

## 4. The Unique Insight

> "Marketing agencies are teams, not individuals. Single-model AI tools fail because they try to do strategy, writing, SEO, ads, and QA with one prompt. CampaignForge's multi-agent architecture mirrors how real agencies work — specialized roles, parallel execution, quality gates — producing enterprise-quality output at SMB prices."

**Why multi-agent wins:**
- Strategist picks angles the Writer would miss
- SEO agent injects keywords the Strategist wouldn't research
- QA agent catches brand violations the Writer normalizes
- Analytics agent feeds performance data back into the next cycle

Single-prompt tools can't replicate this feedback loop.

---

## 5. Market Size

| Segment | Size | Source |
|---------|------|--------|
| **TAM** — AI Marketing Software (2034) | $26.9B | MarketsAndMarkets |
| **SAM** — SMB Marketing Automation (2026) | $3.49B | Grand View Research |
| **SOM** — Freelancers + Small Agencies (US/UK) | $50M | Bottom-up estimate |
| **CAGR** | 28.6% | MarketsAndMarkets |

**Why it's growing:** LLM costs dropped 90% in 18 months. Marketing budgets shifted from agencies to tools. Social APIs opened for programmatic publishing.

---

## 6. What's Built (Live, Deployed, E2E Tested)

| Metric | Count |
|--------|-------|
| API endpoints | 83 across 20 routers |
| LangGraph agent nodes | 11 |
| Database tables | 17 (PostgreSQL, multi-tenant) |
| Backend services | 20 |
| Frontend pages | 19 |
| E2E tests passing | 9/9 |

### Feature Highlights

- **Campaign Pipeline** — Brief → Orchestrator → [Strategy ∥ SEO] → [Content ∥ Ads] → Human Review → QA → Analytics → Publish
- **Real-time SSE streaming** — Watch each agent work live in the dashboard
- **Stripe billing** — 4 tiers with campaign quota enforcement
- **OAuth platform connections** — X, LinkedIn, Meta
- **White-label client portal** — Agencies rebrand as their own
- **Template marketplace** — Community campaign templates (fork, publish, launch)
- **Slack bot** — `/campaignforge create [brief]`
- **REST API** — API key auth for headless usage
- **Competitive intelligence agent** — Analyze competitors, suggest counter-campaigns
- **Autonomous operator** — Goal-driven weekly campaign cycles
- **Visual content generation** — AI images via fal.ai
- **RAG knowledge base** — 171 marketing skills wired into strategy agent
- **Multi-language content** — Generate campaigns in any language
- **A/B variant generation** — Test multiple content versions
- **Enterprise audit log** — Full action trail for compliance
- **Video/podcast script agent** — TikTok, YouTube, Reels, Podcast formats

---

## 7. Competitive Landscape

Two distinct sets of competitors. Conflating them was the flaw in the earlier version of this table.

**Ring 1 — autonomous channel agents (YC-funded, well capitalised).** Verified Aug 2026: Uplane spans ad generation, landing pages and cross-channel spend allocation and publishes a +20–50% ROAS claim; RankAI sells site-growth autopilot to "startups **and agencies**"; Sprites AI sells SEO **plus** paid ads **plus** content **plus** influencer outreach to "entrepreneurs **and agencies**". They are **not** single-function, and Uplane launched under the exact tagline this deck previously used. We do not win these on feature count.

**Ring 2 — the agency platforms our ICP actually pays for today.** This is where we compete, and where the hole is real.

| Capability | Cloud Campaign | Vista Social | SocialPilot | Sendible | **CampaignForge** |
|-----------|----------------|--------------|-------------|----------|-------------------|
| Entry price | $49 | $79 | $30 | $29 | **$49** |
| Agency tier | $229–$349 | $149–$304 | $100–$200 | $299–$750 | **$399** |
| White-label | Free on Team+ | Mid tiers | $100 (reports) | $299 tier + ~$315 add-on | **$399** |
| Seats | Unlimited | 10 at Scale | Unlimited at top | Capped per tier | **3 at Growth** ⚠️ |
| AI scope | Captions | Post-level assistant | Captions | Post-level assistant | **Strategy + SEO + ads + brand QA from one brief** |
| Human approval gate | Approval workflow | Approval workflow | Approval workflow | Approval workflow | **Agent-level, mid-pipeline** |
| Multi-agent transparency | No | No | No | No | **Live SSE dashboard** |

**The wedge:** every incumbent's AI starts *after* the strategy exists. We generate the strategy, the SEO angle, the ad copy and the QA pass as one deliverable, then hand it to whatever they already publish with. We sit above the scheduler rather than replacing it — near-zero switching cost.

**Honest gap:** seat caps are below segment norm, and analytics is not yet real (backlog P0-1). Reporting is the incumbents' core recurring value, so we do not lead with it.

---

## 8. Business Model

Limits below match `PLAN_CONFIG` in `backend/src/agency/services/billing.py` and the live pricing page. Do not edit one without the others.

| Plan | Price | Clients | Posts/mo | Campaigns/mo | Target |
|------|-------|---------|----------|--------------|--------|
| Free | $0 | 1 | 30 | 5 | Trial users |
| Starter | $49/mo | 3 | 200 | 20 | Freelancers with a few retainers |
| Growth | $149/mo | 10 | 1,000 | Unlimited | Small agencies |
| Agency | $399/mo | Unlimited | Unlimited | Unlimited | Multi-client agencies |

A re-meter to client workspaces with unlimited seats is queued as P1-7 in the hardening backlog — the segment prices per workspace, not per post.

**Unit Economics:**
- LLM cost per campaign: ~$0.15–0.30 (Gemini Flash for workers)
- Infrastructure at 100 users: <$50/month (Fly.io auto-stop + Neon free tier + Vercel hobby)
- **Gross margin at scale: 90%+**
- Payback period: <1 month on Starter plan

---

## 9. Tech Stack

| Layer | Technology | Hosting |
|-------|-----------|---------|
| Frontend | Next.js 15 + React 19 + Tailwind + Clerk Auth | Vercel |
| Backend | FastAPI + LangGraph (82 endpoints, 24 routers) | Fly.io |
| Database | PostgreSQL (async, multi-tenant, 18 tables) | Neon Serverless |
| AI Brain | Claude Sonnet (orchestrator, QA) | Anthropic |
| AI Workers | Gemini 2.5 Flash (content, strategy) | Google |
| LLM resilience | 6 providers with per-tier automatic failover | — |
| Payments | Stripe (subscriptions + signature-verified webhooks) | — |
| Email | AgentMail | — |
| Images | fal.ai (flux/schnell) | — |
| CI/CD | GitHub Actions, Playwright E2E | — |

**Capital efficient:** Total infra cost at 100 users < $50/month.

---

## 10. Go-to-Market

**ICP:** social/content agencies of 2–10 people and senior freelancers managing 3–15 client brands. They already pay for a scheduler and already do strategy in a Google Doc with ChatGPT, unbilled. Their constraint is fulfillment hours per client, not content volume.

| Phase | Gate (not a date) | Build | Sell |
|-------|-------------------|-------|------|
| **Make it honest** | Zero non-working features on screen; 5 design partners | P0-4 label stubs, P0-2 billing + tenancy tests, remove placeholder proof | Hand-recruit 5 agencies, free for 90 days |
| **Make it valuable** | One partner runs a full client retainer unassisted | P0-1 real analytics (X + LinkedIn), client-ready branded export | Weekly working sessions; capture before/after hours per client |
| **Make it repeatable** | 10 paying agencies, each ≥3 active client workspaces | P1-7 re-meter to workspaces, white-label domain tested E2E | Convert partners to paid, ship comparison pages, open cold outreach |

### Distribution Channels

Ranked by fit with an agency buyer — full rationale in [competitive-analysis-gtm.md](competitive-analysis-gtm.md).

| Channel | Tactic | Priority |
|---------|--------|----------|
| Founder-led design partners | Direct outreach to 5 agencies; the only source of real logos, quotes and before/after numbers | Now |
| Comparison SEO | "Sendible alternatives", "white-label social media management" — the segment already runs this play on itself; our own SEO agent is the dogfood story | Now |
| Agency-owner communities | Private Slack/FB groups, r/agency, r/socialmedia — where switching decisions get discussed | Wk 4+ |
| Cold email (AgentMail) | <50/day, warmed domain, only after a case study exists | Wk 6+ |
| LinkedIn | Case studies with real before/after metrics from design partners | Wk 6+ |
| Product Hunt | Launch-day spike — sends founders and prosumers, not agency owners | Later |

---

## 11. The Ask

**Raising $500K** on a SAFE at YC standard terms.

| Use of Funds | Allocation |
|-------------|-----------|
| Engineering (full-time hire + LLM costs) | 60% |
| GTM (Product Hunt, content marketing, outreach) | 20% |
| Runway (12 months at current burn) | 20% |

---

## 12. Why Now

1. **LLM costs dropped 90%** — Gemini Flash makes full campaigns cost $0.15 (was $5+ with GPT-4)
2. **Multi-agent frameworks matured** — LangGraph, CrewAI, AutoGen make orchestration production-ready
3. **SMBs priced out of agencies** — Post-2024 recession pushed marketing budgets to tools
4. **Social APIs opened** — X, LinkedIn, Meta now support programmatic publishing
5. **YC competitors proved demand** — Uplane, RankAI and Sprites validated that AI can run marketing execution. They sell to the brand; we sell to the agency serving 15 brands, with white-label and an approval gate they don't have

---

## 13. Metrics We'll Track

| Metric | Minimum for YC | Stretch |
|--------|---------------|---------|
| MRR | $2K | $5K+ |
| Paying users | 20 | 50+ |
| Weekly growth | 10% | 15%+ |
| Campaigns run | 200+ total | 500+ |
| Content pieces generated | 1,000+ | 5,000+ |
| User retention (30-day) | 40% | 60%+ |
| NPS | 30+ | 50+ |
| Time-to-value | < 5 min | < 3 min |

---

## 14. Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| "YC already funded competitors" | Different buyer. They sell execution to the brand; we sell client-fulfillment capacity to the agency — white-label, multi-tenant, approval gate. Claiming they're "single-function" is not defensible as of Aug 2026 |
| "LLM quality inconsistent" | QA agent + human review gate + structured JSON + retry logic |
| "No moat — anyone can build this" | Brand learning data compounds over time; template marketplace = network effects; agency-mode = lock-in |
| "Social API rate limits" | Queue-based publishing, per-platform rate limiting, retry with backoff |
| "Pricing pressure from free tools" | Free tools don't do end-to-end. Our value = time saved (5 min vs 5 weeks) |

---

## 15. Demo Script (60 seconds)

```
0-5s:   "This is CampaignForge. Type one brief, get an entire campaign."
5-15s:  [Type brief: "Launch campaign for Sunrise Coffee new cold brew line"]
15-25s: [Live dashboard — Orchestrator activates, Strategy + SEO run in parallel]
25-35s: [Content Writer generates LinkedIn post, Twitter thread, Instagram caption]
35-45s: [QA Agent scores 8.7/10, flags compliance issue, auto-fixes]
45-55s: [Calendar view — all posts scheduled across 4 platforms]
55-60s: "One brief, a client-ready campaign, under your logo. Take on three more clients without hiring."
```

---

*CampaignForge AI — Replacing agencies, not people.*
