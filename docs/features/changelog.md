# Feature Changelog

Chronological record of feature changes. Newest first.

---

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
