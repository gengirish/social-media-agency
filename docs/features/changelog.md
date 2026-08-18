# Feature Changelog

Chronological record of feature changes. Newest first.

---

## 260817 — Tenant Isolation Sweep (T1.7) + Frontend Build Gate (T0.5)

**Security — six routers were not enforcing `org_id`.** There is no row-level security in this database, so each missing filter was the isolation boundary itself.

- `routers/oauth.py` — `oauth_callback` trusted the request-body `client_id` and attached a `PlatformAccount` to it without checking the client belonged to the caller's org. Now resolved against `org_id` *before* the token exchange, with a 400 for a malformed id (it previously raised a 500 out of the handler).
- `routers/publishing.py` — `publish_now` selected `PlatformAccount` on `client_id`+`platform`+`status` with no `org_id`. Combined with the above this was live, not theoretical: an attacker could insert an account row carrying a victim's `client_id`, and the victim's publish would either 500 permanently (`scalar_one_or_none` on two rows) or post their content using the attacker's token. Now org-scoped and ordered `created_at DESC` with `.first()`, since one org may legitimately hold several accounts per client+platform.
- `routers/comments.py` — `add_comment` did not verify `content_id` belonged to the caller's org.
- `routers/notifications.py` — `mark_read` filtered `user_id` but not `org_id`.
- `routers/reports.py` — `list_reports` accepted `client_id` and checked nothing.
- `routers/portal.py` — `_resolve_org` fell back to non-unique `domain` and `name` columns on an **unauthenticated** route.

**Bugs found while writing the tests:** `routers/comments.py` and `routers/notifications.py` were entirely non-functional — both did `user.id` on the value from `get_current_user`, which returns the JWT payload **dict** in both auth modes. Every route in both files returned 500. New `get_current_user_id` dependency in `dependencies.py`; `comments.py` now resolves the author's display name from the `users` table instead of reading a `full_name` key the payload never had.

**Schema:** `organization.slug` (`VARCHAR(64) UNIQUE`, nullable) added to `db/init.sql`, `models/tables.py`, `db/seed.sql`. New `backend/src/agency/utils/slug.py` generates slugs on both org-creation paths (local signup, Clerk auto-provision). **`db/migrations/260817_org_slug.sql` must be run by hand on existing databases** — `init.sql` only executes on a fresh one. This is the first entry in a new `db/migrations/` directory.

**Also:** `services/billing.py` `_handle_invoice_paid` no longer reports `usage_reset` when no subscription matched the Stripe customer; it returns `{"status": "ignored", "reason": "no_subscription_for_customer"}` and logs a warning.

**Tests:** `backend/tests/test_tenancy_routers.py` — 16 cases, each verified to fail when its own filter is deleted. Suite 181 → **197 passing**.

**Frontend (T0.5):** `typescript.ignoreBuildErrors` and `eslint.ignoreDuringBuilds` removed from `next.config.mjs`. `next build` now type-checks and lints; a planted type error fails it with exit 1. Nothing needed fixing — T0.4's lint pass had already cleared the codebase.

---

## 260817 — Documentation Reconciliation

Docs-only pass. No application code changed. Every count re-derived from source rather than carried forward.

- **Fixed**: Endpoint total was 86 across 21 routers; actual is **82 across 24 routers**. The per-router tables in `api-endpoints.md` were already correct — only the footer and index were wrong
- **Fixed**: `services.md` plan limits contradicted `billing.md`. `services.md` claimed free 2 clients/30 posts, starter 5/100, growth 15/500 — all wrong. `PLAN_CONFIG` is 1/30, 3/200, 10/1000, unlimited. `billing.md` was right
- **Fixed**: `database-schema.md` header said 17 tables while listing 18; actual is **18**
- **Fixed**: Counts across the index — services 21 → **23**, frontend pages 19 → **17**, agent nodes 11 → **9 graph nodes** (7 LLM agents + `human_review` + `compile_output`), integrations 5 → **7**
- **Fixed**: Next.js 14 → **15.5**, React 19, Clerk 7 in `frontend-pages.md` and root `README.md`
- **Fixed**: Root `README.md` project structure was badly stale — claimed 10 routers/36 endpoints, 8 services, 15 tables, 15 pages, 8 agent nodes, Gemini 2.0 Flash
- **Fixed**: `services.md` described `_decrypt_token` as a passthrough stub; it now performs real decryption
- **Added**: `[STUB]` status label and a **Feature Honesty** table in the index, marking every feature whose route works but whose data is placeholder — analytics metrics, trends, RAG, Instagram publish, Instagram metrics (hardening backlog P0-4)
- **Added**: `services.md` entry for `services/platform_metrics.py` — real X/LinkedIn/Facebook fetchers, written but **imported by nothing**; documents the `unavailable`-not-zeros contract that integration must honour
- **Added**: `billing.md` section documenting Stripe webhook signature verification as implemented (raw body + `construct_event`, 503 when unconfigured, 400 on missing/invalid signature) — P0-3 is satisfied in code
- **Added**: `auth-and-rbac.md` middleware stack table and an explicit warning that there is **no row-level security** — isolation depends entirely on every query filtering `org_id`
- **Added**: `frontend-components.md` entries for `AnalyticsTracker` and `lib/analytics.ts`, both previously undocumented
- **Added**: `integrations.md` entries for fal.ai image generation (verified live — real call to `queue.fal.run/fal-ai/flux/schnell`) and Slack; LLM table corrected from 3 providers to **6**, reframed as per-tier fallback chains rather than per-agent assignment
- **Added**: `integrations.md` note that `EXA_API_KEY` is configured but read by no service
- **Added**: `billing.md` note that `STRIPE_PRICE_STARTER` / `_GROWTH` / `_AGENCY` are read by `config.py` but absent from `.env.example`
- **Added**: `workers.md` notes on `_mark_campaign_failed` and the silent `MemorySaver` checkpointer fallback
- **Changed**: `frontend-pages.md` root `/` was documented as an auth redirect; it is a ~541-line marketing landing page. Its placeholder logos and testimonials are self-labelled "Placeholder" in the UI, but the "Trusted by teams who ship campaigns weekly" heading still asserts traction that does not exist (P1-1)
- **Note**: `websocket.md` already described SSE correctly. The filename is the only WebSocket artefact left; added a header note rather than renaming

## 260729 — Multi-Provider LLM Chain

- **Added**: Six LLM providers — `anthropic` and `google` via native SDKs, plus `openai`, `nvidia` (NIM), `openrouter`, and `bonsai` as OpenAI-compatible endpoints through `ChatOpenAI(base_url=...)`. No new dependencies
- **Added**: Runtime failover — the primary provider for a tier attaches every other configured provider via LangChain `.with_fallbacks()`, so a transient gateway 503 no longer fails a campaign
- **Added**: `LLM_PROVIDER_ORDER`, `LLM_{TIER}_PROVIDER` (pins a tier, disabling its fallbacks), `LLM_{TIER}_MODEL` (primary only — model ids are provider-specific)
- **Added**: `GET /api/v1/health/llm` — resolved provider, model, and fallback chain per tier; never returns key material
- **Added**: `GEMINI_API_KEY` accepted as an alias for `GOOGLE_API_KEY`
- **Changed**: Default Gemini model `gemini-2.0-flash` → `gemini-2.5-flash`. 2.0-flash returns HTTP 429 (quota exceeded) on current free-tier keys
- **Changed**: NVIDIA NIM default model is `deepseek-ai/deepseek-v4-flash`; `meta/llama-4-maverick-17b-128e-instruct` reached end of life 2026-07-27 and returns HTTP 410
- **Fixed**: With no provider key set, the old code built a client with an empty API key and died inside the first agent. `get_llm()` now raises immediately, naming the variables to set
- **Fixed**: `GET /api/v1/health/db` always returned 500 — SQLAlchemy 2.x rejects a bare `"SELECT 1"` string; now wrapped in `text()`

## 260728 — Product Analytics for Beta Metrics

- **Added**: `product_event` table + `ProductEvent` model — usage event stream, separate from `audit_log` (compliance) — with indexes on org/name/user/campaign/session
- **Added**: `services/product_analytics.py` — event capture (`track`, `track_detached`) and every metric in `docs/beta-testing-plan.md` §7: time-to-first-campaign, campaign completion/failure rate, agent step drop-off funnel, feature adoption, session duration, D1/D7/D14 return rate, errors by endpoint
- **Added**: `POST /api/v1/events` — batched browser ingest, allowlisted to four client-writable event names so a client cannot inflate pipeline counts; client timestamps clamped to server now
- **Added**: `GET /api/v1/beta-metrics` — §7 dashboard, always org-scoped (cross-tenant rollup is not exposed over HTTP)
- **Added**: `RequestMetricsMiddleware` — in-memory request/error counters for true error rates, plus persisted 4xx/5xx events (401/404 skipped as noise)
- **Added**: Frontend `lib/analytics.ts` + `AnalyticsTracker` mounted in the dashboard layout — session lifecycle, page views, `trackFeature()` on campaign create, client create, magic-brief client create, and content publish
- **Fixed**: A crashed pipeline left its campaign stuck in `running` forever. `_mark_campaign_failed` now moves campaign and workflow to `failed` and records the failure, so the failure-rate metric reflects reality

## 260328 — 40-Feature YC Implementation (Phases 1-4)

### Phase 1: "Make Them Pay"
- **Added**: Stripe production wiring — configurable Price IDs via env vars, campaign quota enforcement (402 on limit)
- **Added**: Settings backend — GET/PATCH org settings, platform accounts listing
- **Added**: Calendar drag-and-drop — HTML5 DnD rescheduling, week view toggle, platform color coding
- **Added**: One-click repurpose — POST /content/{id}/repurpose for platform-adapted variants
- **Added**: Client reports — POST/GET /reports/clients/{id} with period-based report generation
- **Added**: OAuth connect flow — GET/POST /oauth/{platform}/authorize|callback for X/LinkedIn/Meta
- **Added**: Publishing enhancements — retry logic (3 attempts), token decryption stub

### Phase 2: "Make Them Stay"
- **Added**: Analytics agent wired into LangGraph pipeline (compile_output → analytics → END)
- **Added**: Performance feedback loop — analytics_fetcher service, GET /content/{id}/analytics
- **Added**: Campaign templates — GET/POST /templates/{id}, launch from template
- **Added**: Content A/B variants — POST /content/{id}/variants with variant grouping
- **Added**: Comment threads — full CRUD on content comments
- **Added**: Notification system — model, service, router, NotificationsBell component in header
- **Added**: Content recycling — GET /content/suggestions for top performers
- **Added**: Trend intelligence — GET /campaigns/trends, platform-specific trending topics

### Phase 3: "Make It Defensible"
- **Added**: Brand intelligence dashboard — GET /brand-analytics/clients/{id}/intelligence
- **Added**: Cross-campaign learning — GET /brand-analytics/cross-learning, industry benchmarks
- **Added**: RAG knowledge base — keyword retrieval from 171 marketing skills, wired into strategy agent
- **Added**: Multi-language content — target_languages in CampaignState, content writer language adaptation
- **Added**: Visual content generation — POST /content/{id}/generate-image via fal.ai
- **Added**: White-label portal — portal_enabled, GET/PATCH /portal/{org_slug}/...
- **Added**: Template marketplace — marketplace listing, fork, publish endpoints
- **Added**: Slack bot — /integrations/slack/events + /commands
- **Added**: REST API — API key auth middleware, X-API-Key header, /public/* routes
- **Added**: Webhooks — register/list/delete webhook config
- **Added**: Competitive intelligence — POST /competitive/clients/{id}/scan

### Phase 4: "Moonshots"
- **Added**: Autonomous campaign operator — POST /campaigns/autonomous, goal-driven weekly cycles
- **Added**: Client acquisition engine — POST /acquisition/outreach, 3-email sequences
- **Added**: Bid optimization service — LLM-based ad performance analysis
- **Added**: Video/podcast script agent — POST /content/video-script (TikTok/YouTube/Reels/Podcast)
- **Added**: Enterprise audit log — AuditLog model, log_action service, GET /audit

### Infrastructure
- **New files**: ~20 backend modules (routers, services, agents), 4 frontend pages/components
- **Modified**: ~20 existing files
- **New DB tables**: Notification, AuditLog
- **New env vars**: 10 (OAuth keys, fal.ai, Slack, Exa)
- **Route count**: 38 → 83 endpoints
- **Service count**: 8 → 20

## 260324 — End-to-End Multi-Agent Pipeline Fixes

- **Fixed**: SSE stream auth — accepts JWT via `?token=` query param for EventSource compatibility
- **Added**: AgentRun tracking — inserts DB row per agent node completion during campaign pipeline
- **Added**: Human review UI — approve/revise buttons in LiveAgentDashboard with PATCH to backend
- **Added**: Brand learning wiring — `update_brand_learnings()` called on campaign completion
- **Changed**: Analytics page — replaced "Coming Soon" with real KPI dashboard (stats, content pipeline, campaign status, agent metrics)
- **Changed**: Settings page — replaced static cards with tabbed UI (General, Platforms, API Keys, Notifications)
- **Changed**: Agent stream client — uses Clerk token parameter instead of localStorage
- **Fixed**: CI pipeline — removed `continue-on-error: true` so failures are caught
- **Changed**: Team invite — honest response message + best-effort AgentMail email
- **Added**: Full feature documentation — all 10 feature doc files created from codebase scan

## 260324 — Clerk Authentication Integration

- **Added**: Clerk JWT verification (RS256 + JWKS) in backend `get_current_user`
- **Added**: Auto-provisioning of users/orgs on first Clerk login
- **Added**: `ClerkTokenSync` component to wire Clerk tokens into API client
- **Added**: Clerk middleware for frontend route protection
- **Added**: E2E test auth via Clerk sign-in tokens (bypasses instance-level MFA)
- **Changed**: `get_org_id` fallback to user dict for Clerk sessions

## 260324 — Feature Documentation Initialized

- **Added**: `feature-docs` skill — Living documentation system
- **Added**: `docs/features/` directory — Central location for all feature documentation
