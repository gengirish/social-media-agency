# CampaignForge AI — Pre-Launch Hardening Backlog

<!-- created: 260701 -->

**Goal:** Move CampaignForge from "impressive MVP skeleton" to "sellable, trustworthy SaaS."
**Source:** Code audit (260701) — see verdict below.
**Sequencing rule:** Do P0 before charging anyone. P1 before public launch. P2 = post-launch.

## Verdict recap
- **Real & working:** LangGraph 7-agent pipeline, LLM routing, content generation, X/LinkedIn/FB publishing, Stripe billing, fal.ai images, SSE dashboard, multi-tenant + Clerk.
- **Hollow:** analytics metrics (returns zeros), trends (hardcoded), RAG (keyword not vector), Instagram publish, webhooks, competitive intel, landing-page social proof.
- **Biggest risk:** ~3 test files for 83 endpoints / 20 services.

Legend — Effort: S ≤1d · M 2–4d · L 1–2wk. Impact: 🔴 critical · 🟠 high · 🟡 medium.

---

## P0 — Blockers (do before taking a single payment)

### P0-1 · Make analytics real 🔴 · L
**Problem:** `services/analytics_fetcher.py:37` returns all zeros. The "close the loop / feed the next brief" value prop is non-functional. Agencies pay for ROI proof.
**Do:**
- Implement real metric pulls: X (v2 metrics), LinkedIn (ugcPosts/organizationalEntity stats), Meta Graph insights.
- Persist real `AnalyticsSnapshot` rows; wire the scheduler to refresh published content daily.
- Feed real `previous_performance` into `autonomous_operator.plan_autonomous_cycle`.
**Acceptance:** A published post shows non-zero impressions/engagement pulled from the live platform API within 24h; dashboard reflects it; zero fabricated numbers.

### P0-2 · Test the money + tenancy paths 🔴 · L
**Problem:** Near-zero coverage on billing, quota, and tenant isolation — the paths where bugs = lost revenue or cross-tenant data leaks.
**Do:**
- Stripe webhook handlers (checkout.completed, invoice.paid, subscription.deleted/updated) with signature verification.
- Quota enforcement (402 on limit) + usage reset on new period.
- Tenant isolation middleware: assert org A can never read org B's clients/content/campaigns.
**Acceptance:** ≥40–50% coverage on `services/billing.py`, `middleware/tenant.py`, and campaign/content routers; a cross-tenant access test exists and passes (denies).

### P0-3 · Stripe webhook signature verification 🔴 · S — ✅ VERIFIED IMPLEMENTED 260817
**Problem:** Confirm `handle_webhook` validates `Stripe-Signature`. Unverified webhooks = anyone can grant themselves a paid plan.
**Finding:** already correct in `routers/billing.py`. Missing secret → 503 (fails closed); missing `stripe-signature` header → 400; `stripe.Webhook.construct_event` runs against the **raw** body via `await request.body()`; `ValueError` → 400, `SignatureVerificationError` → 400. Only verified events reach `billing.handle_webhook()`.
**Acceptance:** met in code. **Caveat:** the regression test asserting it (`tests/test_billing.py`) does not currently run — blocked on P0-2's missing conftest fixtures. Verification is real but unguarded against future regression.

### P0-4 · Hide or label all stubs 🔴 · M
**Problem:** Selling faked features (trends, webhooks, Instagram, competitive intel, RAG-as-vector) is a trust/legal risk.
**Do:** Feature-flag off, or badge "Coming soon" in UI, or remove endpoints. No stub should look production-ready.
**Acceptance:** Every user-facing feature either works with real data or is clearly marked unavailable. Audit list has zero "looks real but isn't."

---

## P1 — Launch readiness (before public launch)

### P1-1 · Replace fake social proof 🟠 · M
**Problem:** `frontend/src/app/page.tsx` ships placeholder logos + invented testimonials/"$6k/mo" quote. Fabricated proof erodes trust and risks FTC issues.
**Do:** Recruit 3–5 design partners; use real quotes/logos with permission, or remove the section until you have them.
**Acceptance:** No invented testimonials or customer logos on the live site.

### P1-2 · Instagram publishing (or drop the claim) 🟠 · M
**Problem:** `_publish_instagram` is not implemented but "Meta (Facebook & Instagram)" is a headline landing-page claim.
**Do:** Implement Graph API container+publish (media required), OR remove Instagram from marketing copy until shipped.
**Acceptance:** Claim matches capability.

### P1-3 · Pick ONE ICP + sharpen the wedge 🟠 · M (strategy)
**Problem:** "Replace your agency for $49" competes head-on with Jasper/Copy.ai/Ocoya. Weak positioning.
**Do:** Focus on **small agencies via white-label** (transparent multi-agent + human-in-the-loop as the differentiator). Rework hero, pricing emphasis, onboarding around that ICP.
**Acceptance:** Landing page + first-run flow speak to one buyer; white-label is a first-class, tested path.
**Status 260817 — partially done.** ICP set to agencies/freelancers running 3–15 client brands. Hero, plan blurbs, `README.md` and `yc-pitch.md` (positioning, competitive table, GTM, demo script) rewritten to the agency message; the old tagline also collided verbatim with Uplane (YC F25). **Still open:** first-run/onboarding flow, pricing emphasis (see P1-7), and white-label as a tested path. Analysis: [competitive-analysis-gtm.md](competitive-analysis-gtm.md).

### P1-4 · Real trends or remove 🟠 · S
**Problem:** `services/trends.py` returns a hardcoded list claiming "Exa in production."
**Do:** Wire Exa/real source, or remove the feature + endpoint + UI.
**Acceptance:** Trends reflect live data or don't exist.

### P1-5 · Error handling + observability on critical routes 🟠 · M
**Problem:** e.g. `routers/campaigns.py:355` `pass # log in production`. Silent failures in the pipeline are hard to debug in prod.
**Do:** Structured error logging, Sentry (or similar), and user-visible failure states in the SSE dashboard.
**Acceptance:** A forced agent failure surfaces a clear error to the user and a logged event.

### P1-7 · Re-meter pricing to client workspaces 🟠 · M — added 260817
**Problem:** plans meter on `posts_limit` and cap seats (Growth = 3). Agencies forecast in clients, not posts, and the whole competing segment ships unlimited or near-unlimited users — Cloud Campaign gives unlimited users at $49 while Growth caps at 3 for $149. Unpredictable bills at the moment a buyer adds a client is how agency tools get churned. Evidence and competitor pricing in [competitive-analysis-gtm.md](competitive-analysis-gtm.md).
**Do:**
- Change the meter to client workspaces; drop `posts_limit` as a billing gate (keep a per-org rate limit for abuse — at $0.15–0.30/campaign, volume is not the margin risk).
- Unlimited seats on all paid tiers.
- Proposed shape: Solo $49 / 3 workspaces · Studio $149 / 10 · Agency $349 / 30 + white-label domain + API, overage per workspace above 30.
- Update `PLAN_CONFIG`, `db/init.sql` + `models/tables.py` if columns change, the hardcoded pricing on `frontend/src/app/page.tsx`, `docs/features/billing.md`, and `yc-pitch.md` §8 together.
**Acceptance:** one meter, stated identically in code and on the pricing page; no seat cap on a paid tier; an existing subscriber's limits migrate without a support ticket.
**Blocked on:** confirming the Agency price move from $399 to $349 does not conflict with a quote already given.

### P1-6 · Reconcile docs with reality 🟡 · S — ✅ DONE 260817
**Problem:** `README.md` said 36 endpoints/8 agents/15 tables; feature docs said 83/11/17. Both were wrong.
**Verified actual:** 82 endpoints · 24 routers · 18 tables · 23 services · 17 pages · 9 LangGraph nodes.
**Done:** all 12 `docs/features/*.md` + `README.md` + `yc-pitch.md` corrected and restamped `verified: 260817`. Added a `[STUB]` label and Feature Honesty table so P0-4's "looks real but isn't" list is at least *documented* — note this does **not** close P0-4, which requires the UI itself to stop presenting stubs as working.
**Also corrected:** `services.md` plan limits contradicted `PLAN_CONFIG` and `billing.md`; `platform_metrics.py` was undocumented; Stripe webhook signature verification was already implemented (see P0-3 below).
**Acceptance:** met — counts match a fresh grep of the codebase.

---

## P2 — Post-launch depth

- **P2-1 · Real RAG** 🟡 M — pgvector embeddings for the knowledge base (currently keyword match).
- **P2-2 · Webhooks for real** 🟡 M — add webhooks table + delivery/retries + signing.
- **P2-3 · Competitive intel grounding** 🟡 L — back `competitive/scan` with real data (SERP/site crawl) instead of LLM guessing.
- **P2-4 · Broaden test coverage** 🟡 L — agents, publishing, reports; add CI gate.
- **P2-5 · Deliverability/limits** 🟡 M — per-platform rate limits, token refresh flows, publish backoff.

---

## Suggested 6-week cut
- **Wk 1–2:** P0-2, P0-3, P0-4 (tests + webhook security + hide stubs).
- **Wk 2–4:** P0-1 (real analytics) — the big one.
- **Wk 4–5:** P1-1, P1-3, P1-4 (proof, positioning, trends).
- **Wk 5–6:** P1-2, P1-5, P1-6 + recruit design partners in parallel from day 1.

## Open questions
1. ~~Target ICP confirmed as small agencies (white-label), or self-serve solo marketers?~~ **Resolved 260817:** small agencies + freelancers managing 3–15 client brands. Wedge sits *above* the scheduler (export-first), so P0-1 analytics and P1-2 Instagram are no longer launch blockers for the first cohort.
2. Any design partners already lined up (needed for P1-1 real proof)?
3. Is Razorpay (used elsewhere in your stack) or Stripe the intended payment rail for launch? README/billing assume Stripe.
