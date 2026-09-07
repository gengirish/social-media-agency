# CampaignForge AI — Build Status Deep Dive

<!-- created: 260907 -->

Verified against code on 260907, not against prior docs. Where this contradicts [stub-audit-260817.md](stub-audit-260817.md), that doc is three weeks stale and this one is current.

**Method:** ran the gates; traced every service to its importers; traced all 79 frontend API-client methods to their call sites; read each agent, router, and background loop. Findings below are code-verified, with the check noted.

## Current gates

| Gate | 260817 | 260907 | Δ |
|---|---|---|---|
| `pytest tests/ -q --no-cov` | 181 passed | **216 passed** | +35 |
| `ruff check src/ tests/` | 290 | **0 — all checks passed** | −290 |
| `mypy src/agency/ --ignore-missing-imports` | 409 errors / 61 files | **414 errors / 61 files** | +5 |
| Endpoints | 82 | **83** | +1 |
| Production | — | API + frontend both live, 200 | — |

Ruff going 290 → 0 is the headline. Mypy is the one gate moving the wrong way, though `strict = true` in `pyproject.toml` makes 414 a soft number — most will be missing annotations rather than real type errors.

---

## 1. Built and working

### Agent pipeline — the strongest part of the codebase

| Component | Verified |
|---|---|
| LangGraph `StateGraph`, 9 nodes | `agents/graph.py` |
| Two real parallel fan-outs (Strategy ∥ SEO, Content ∥ Ad Copy) | graph edges |
| `interrupt_before=["human_review"]` — genuine suspend/resume | graph compile |
| `AsyncPostgresSaver` checkpointing, `MemorySaver` fallback | `graph_runtime.py` |
| Singleton compiled graph at startup | `get_runtime_compiled_graph()` |
| Conditional routers: post-review 3-way, post-QA loopback capped at 2 | `_route_after_human_review`, `_route_after_qa` |
| All 7 agents make real LLM calls | 3 LLM refs each in `strategy`, `seo`, `content_writer`, `ad_copy`, `qa_brand`, `orchestrator`, `analytics` |

### LLM routing

3 tiers × **7 providers** (Anthropic, Google native; OpenAI, NVIDIA, OpenRouter, Bonsai, **Groq** — added 260818). Per-tier `.with_fallbacks()` chains, blank key disables a provider, missing config raises with variable names. `GET /health/llm` reports the resolved chain. `llm_provider` has 17 importers — the most-depended-on module in the codebase, and correctly the only LLM entry point.

### Fully working end-to-end

- **Campaigns** — create, list, detail, SSE stream, human review gate, review decision resume.
- **Magic Brief** — real: fetches the URL over httpx (15s timeout, follow-redirects), then `get_worker_llm(0.3)`. Not a stub.
- **Content** — repurpose (batched into one call per many platforms — there's a test for it), variants, approve, patch.
- **Publishing** — X, LinkedIn, Facebook. Real API calls.
- **Platform metrics** — genuinely calls `api.x.com/2/tweets`, `api.linkedin.com/v2/socialActions` + `organizationalEntityShareStatistics`, `graph.facebook.com/v19.0` + `/insights`.
- **Calendar** — drag-and-drop is real (`DragEvent`, custom MIME type, persists).
- **Scheduler** — background loop publishes due content; daily analytics refresh guarded to once per UTC day.
- **OAuth backend** — full token exchange + **Fernet encryption at rest** (`access_token_enc`). Backend is complete.
- **Billing** — Stripe checkout, 4 tiers, webhook dispatch, limits.
- **Auth** — Clerk RS256 + JWKS + auto-provisioning, HS256 local fallback, `X-API-Key`, `TenantMiddleware`.
- **Email** — `email_service.py` extracted 260818, AgentMail-backed, reports delivery honestly (221 lines of tests).
- **Webhooks** — DB-backed, HMAC-signed, delivery tracking.
- **Knowledge base** — real cosine similarity over `knowledge_embedding`, degrades to keyword scoring with `retrieval_mode` labelled on every item.
- **Trends** — Exa-backed with per-item source URL and `provenance`.
- **Product analytics** — `product_event`, server-authored pipeline events, client-writable allowlist.

### Review buttons — fixed since the audit

Audit finding #59 said the review buttons used raw `fetch` and only `console.error`d on failure. **Now fixed**: `live-agent-dashboard.tsx:63-81` uses `api.submitReview`, with per-decision loading state, disabled-while-submitting, `toast.success` and `toast.error`. The warning I put in the beta guide is stale — remove it.

---

## 2. Built on the backend, no UI

**The largest single gap. 42 of 79 frontend API-client methods have zero call sites in `app/` or `components/`.** The backend works; nobody can reach it from the product.

| Feature | Backend | UI |
|---|---|---|
| **Client portal** | 3 endpoints, white-label aware | **No `/portal` route exists in `frontend/src/app` at all** |
| **White-label config** | `white_label.py`, GET + PUT | `getWhiteLabel`/`updateWhiteLabel` never called |
| **Webhooks** | 4 endpoints, HMAC, delivery log | `getWebhooks`/`createWebhook`/`deleteWebhook`/`getWebhookDeliveries` all unused |
| **Comments** | 3 endpoints | `getComments`/`addComment`/`deleteComment` unused |
| **Reports** | `reporting.py`, 2 endpoints | `generateReport`/`getReportPeriods` unused |
| **Template marketplace** | fork / publish / marketplace list | Only `getTemplates` + `launchTemplate` used, and `/templates` has no nav link |
| **Competitive scan** | `competitive_intel.py`, Exa, source-gated | `runCompetitiveScan` unused (only `getClientIntelligence` is wired) |
| **Autonomous operator** | `autonomous_operator.py`, real | `createAutonomousCampaign` unused |
| **Video script** | endpoint hardened (client_id required) | `createVideoScript` unused |
| **Content analytics / suggestions** | endpoints exist | `getContentAnalytics`/`getContentSuggestions` unused |
| **Beta metrics** | `GET /beta-metrics`, ~58 fields | `getBetaMetrics` unused — the whole surface is write-only |
| **Audit log** | endpoint exists | `getAuditLogs` unused |
| **A/B variants** | endpoint exists | `generateVariants` unused |
| **Team role update** | endpoint exists | `updateTeamMemberRole` unused |
| **Platform disconnect** | endpoint exists | `disconnectPlatformAccount` unused |
| **Health checks** | 3 endpoints | `health`/`healthDb`/`healthLlm` unused |

Correcting my own beta guide: it told testers to visit `/portal/{org_slug}`. **That page does not exist.** The portal is API-only.

### The OAuth dead end

The most consequential item here. Backend `routers/oauth.py` is complete — authorize URL, token exchange, Fernet encryption, disconnect. But:

- `settings/page.tsx` opens the authorize URL in a new tab
- **no route under `frontend/src/app` matches `*callback*` or `*oauth*`**
- `api.oauthCallback` is declared and never called

So **platform connection cannot be completed from the UI.** Every "connect an account" affordance dead-ends, which in turn blocks publishing and metrics for anyone who hasn't had credentials inserted directly. This is one small route away from unblocking three features.

---

## 3. Not built

### Dead code — defined, zero callers (re-verified today)

| Function | Callers |
|---|---|
| `services/team.py::check_permission` | **0** — RBAC is entirely unenforced |
| `services/ad_optimization.py::analyze_ad_performance` | **0** — whole module has 0 importers |
| `services/audit.py::log_action` | 0 (only a comment referencing it) |
| `services/notifications.py::create_notification` | 0 (only comments) |

### Missing features

Instagram publishing (`_publish_instagram` gated) · TikTok publishing (no publisher) · Instagram metrics · notification producers · logo upload · Slack campaign creation · `performance_score` producer · Analytics-agent insights (needs measured data first).

---

## 4. Built but broken

These are the ones that will burn a tester or a customer, ranked by consequence.

### 4.1 Scheduler pins Neon awake 24/7 — cost defect

`services/scheduler.py:57` runs `await asyncio.sleep(60)` in a `while` loop, and each tick opens a session and runs a `SELECT` over `ContentPiece` (`_process_due_content`). Neon's autosuspend is minutes; **a 60-second query interval means it can never suspend.** Combined with `min_machines_running = 1` in `fly.toml`, both the Fly machine and the Neon compute bill continuously regardless of traffic.

This violates the standing rule: never add a recurring job whose interval is shorter than the idle timeout of anything it touches. The fix is not to lengthen the sleep blindly — scheduled publishing needs minute-ish granularity — but to make the tick cheap or event-driven: compute the next due `scheduled_at` once, sleep until then, and wake early only when something is scheduled. With no scheduled content, that's zero queries instead of 1,440/day.

Worth running the `idle-cost-audit` skill against the actual Neon bill to size it before changing anything.

### 4.2 Cross-tenant data leak in industry benchmarks

`services/cross_learning.py` joins `AnalyticsSnapshot → ContentPiece → Client` filtered on `Client.industry` **with no `org_id` predicate**. There is no row-level security behind it. `GET /brand-analytics/cross-learning?industry=X` therefore aggregates other tenants' analytics.

Flagged in the audit as "arguably intended (cross-org benchmarking)" and left pending a decision. It is still open, and it is still the only query in the codebase that breaks the project's own every-query-filters-on-`org_id` rule. Two honest resolutions: scope it to the caller's org, or keep it cross-org behind an explicit k-anonymity floor (say, suppress below 5 contributing orgs) and say so in the API. Leaving it undecided is the worst of the three.

### 4.3 Stripe plan changes silently discarded

`services/billing.py:203` — `_handle_subscription_updated` is `return {"status": "noted"}`. It is registered in the webhook handler map, so upgrades, downgrades, and `past_due` transitions all return success-shaped bodies and change nothing. A customer who downgrades keeps their old limits; one who upgrades doesn't get new ones until checkout runs again.

Was assigned to T1.7 on 260817. Still a no-op.

### 4.4 Image generation can never succeed

`services/image_generation.py:50` posts to `https://queue.fal.run/...`, which returns `{request_id, status_url}` with HTTP 200 — never `{"images": [...]}`. The parser cannot match, so every call falls through to `{"status": "error"}`. The sync endpoint is `https://fal.run/...`. Reported 260817, unchanged. One-line fix, needs a `FAL_API_KEY` to verify.

### 4.5 Templates drop their configuration

`/templates` has zero inbound links (nav has 9 items, none of them templates). `launchTemplate` redirects to `/campaigns/new?template=…`, and `campaigns/new/page.tsx` **never reads `searchParams`** — verified today. Channels and objective are silently dropped; the user lands on a blank wizard.

### 4.6 Magic Brief unreachable

Complete, working, LLM-backed feature with no entry point in the app. URL-only.

### 4.7 Repurpose can persist unparsed model output

`routers/content.py` converts an LLM JSON parse failure into a real `ContentPiece` whose `body` is raw model output — possibly prose or code fences — and returns `{"status": "repurposed"}` with no error signal.

---

## 5. Documentation drift

| Doc says | Reality |
|---|---|
| `CLAUDE.md`: "there is no `.claude/` directory in this repo" | **`.claude/` exists** with `agents/`, `commands/`, `rules/`, `skills/`, `training/`, `workflows/`, `mcp.json.example`. Commit 7d1299b mirrors `.claude` → `.cursor`, so both are live. |
| `docs/features/README.md`: 82 endpoints, 18 tables, 23 services | 83 endpoints, **21 tables**, 24 service modules |
| `docs/features/websocket.md`: WebSocket | SSE (known, long-standing) |
| README: "6 providers" in places | 7 since Groq landed |
| `beta-testing-plan.md` §5 | 5 test cases fail by design — see beta guide Appendix A |

Also: schema is raw SQL, but `db/migrations/` now holds two migrations (`260817_org_slug.sql`, `260818_schema_catchup.sql`) — a third place schema changes must land, alongside `db/init.sql` and `models/tables.py`. Commit 41d19f7 documents this as a "three-edit rule".

---

## 6. What I'd fix, in order

1. **OAuth callback route** — one frontend route unblocks platform connection, publishing, and metrics for every user. Highest ratio of value to effort in the repo.
2. **Scheduler wake interval** — currently costing money every minute of every day for nothing.
3. **`_handle_subscription_updated`** — real revenue consequences; a downgrade that doesn't take effect is a refund conversation.
4. **Decide on `cross_learning` org scoping** — a leak or an intended feature, but not undecided.
5. **Two nav links** (Magic Brief, Templates) + read `searchParams` in `campaigns/new` — three small changes that surface two finished features.
6. **fal.ai URL** — one line.
7. **Portal UI**, or stop describing the portal as a user-facing feature.

Items 1, 5, and 6 are roughly a day together and would change what a demo or beta can honestly cover.

---

## Corrections to my own earlier docs

- [beta-testing-guide-260907.md](beta-testing-guide-260907.md) §3 Track 3.4 sends testers to `/portal/{org-slug}` — **no such route exists**. Remove or rewrite as API-only.
- Same guide, §4 "Review buttons may fail silently" — **fixed since the audit**, toasts and loading states are present. Remove.
- Same guide, §4 white-label: branding config has no UI either, not just logo upload.

---

## Unresolved

- Is the portal meant to be a hosted page in this app, or is API-only deliberate for embedding in an agency's own site?
- Is cross-org benchmarking an intended feature? The answer decides whether 4.2 is a leak or a spec.
- Was `min_machines_running = 1` chosen to avoid cold starts on the review gate? If so, the scheduler cost is a knock-on of that decision and should be priced deliberately.
- 414 mypy errors under `strict = true` — is the intent to reach zero, or is strict aspirational? It affects whether that gate belongs in CI as a blocker.
- Nothing reads `beta-metrics` back. Is a dashboard planned, or is querying `product_event` directly the intended workflow?
