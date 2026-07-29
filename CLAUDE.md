# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repo Is

**CampaignForge AI** — a multi-tenant SaaS that runs a full marketing campaign (strategy → SEO → content → ads → QA → publish) through a LangGraph agent pipeline with a human review gate.

The repo has **two distinct layers**. Know which one a task belongs to before starting:

1. **The product** — `backend/` (FastAPI + LangGraph), `frontend/` (Next.js 15), `db/`, `docker/`. Normal software engineering.
2. **The marketing agency layer** — `.cursor/` (agents, skills, commands, workflows) + `campaigns/`. Prompt/config assets used to *run* marketing work, not application code. See [Marketing Agency Layer](#marketing-agency-layer).

## Deployment

| Environment | URL | Platform |
|---|---|---|
| Frontend (production) | `https://campaignforge.intelliforge.tech` | Vercel |
| Backend API (production) | `https://campaignforge-api.fly.dev` | Fly.io (app `campaignforge-api`, region `sin`) |
| Database | Neon serverless PostgreSQL | Neon |

`campaignforge.intelliforge.tech` is the canonical app URL — use it for links, env vars, OG/canonical URLs, redirects, sitemaps, and email links (mirrors `.cursor/rules/deployment-domains.mdc`).

Backend config lives in [backend/fly.toml](backend/fly.toml) — note `internal_port = 8080` (the container listens on 8080; local dev uses 8001). Frontend build override is in [frontend/vercel.json](frontend/vercel.json): it patches a missing `page_client-reference-manifest.js` after `next build`. Do not remove that workaround without verifying the Vercel build still succeeds.

CI is [.github/workflows/ci.yml](.github/workflows/ci.yml) (backend lint/type/test, frontend lint/build, E2E). There is **no deploy job** — deploys are manual (`fly deploy` from `backend/`, Vercel Git integration for `frontend/`).

## Commands

### Backend (`backend/`, Python 3.12+)

```bash
pip install -e ".[dev]"
uvicorn agency.main:app --reload --port 8001   # API on :8001, docs at /api/docs

ruff check src/ tests/
mypy src/agency/ --ignore-missing-imports      # pyproject sets strict = true
pytest tests/ -v --tb=short
pytest tests/test_agents/test_graph.py::test_name -v   # single test
pytest tests/ --no-cov                                 # skip coverage output
```

`pytest` is preconfigured with `asyncio_mode = "auto"` and `--cov=src/agency`, so async tests need no marker.

### Frontend (`frontend/`, Node 18+)

```bash
npm install
npm run dev            # :3000
npm run lint
npm run build
npm run test:e2e                            # Playwright; auto-starts dev server
npx playwright test e2e/campaigns.spec.ts   # single spec
npm run test:e2e:ui
```

E2E needs a running backend. Set `PLAYWRIGHT_SKIP_WEBSERVER=1` to test against an already-running frontend. `e2e/global-setup.ts` runs first as a Playwright project dependency.

### Full stack via Docker

```bash
docker compose -f docker/docker-compose.yml up   # postgres, redis, backend :8001, frontend :3000
```

Postgres auto-runs `db/init.sql` then `db/seed.sql` on first boot. To reset, delete the `pgdata` volume.

### Dates

Never use model knowledge for `YYMMDD` dates. Run `Get-Date -UFormat "%y%m%d"` (PowerShell) or `date +%y%m%d` (bash).

## Architecture

### Agent pipeline (`backend/src/agency/agents/`)

```
Orchestrator → [Strategy ∥ SEO] → [Content ∥ Ad Copy] → Human Review → QA/Brand → Compile → Analytics
```

- [graph.py](backend/src/agency/agents/graph.py) defines the LangGraph `StateGraph`. Strategy/SEO run in parallel; Content/Ad Copy run in parallel and both consume Strategy + SEO output.
- The graph compiles with `interrupt_before=["human_review"]` — execution **pauses** there and resumes when a review decision lands via `PATCH /api/v1/campaigns/{id}/review`.
- Two conditional routers control flow: `_route_after_human_review` (approve / revise_content / revise_ads) and `_route_after_qa`, which loops critical QA failures back to Content or Ad Copy, capped at `retry_count >= 2`.
- [graph_runtime.py](backend/src/agency/agents/graph_runtime.py) holds the **singleton compiled graph**, initialized in the FastAPI `startup` hook. Call `get_runtime_compiled_graph()`; never recompile per request. Checkpointing uses `AsyncPostgresSaver` over `NEON_DATABASE_URL`, silently falling back to `MemorySaver` if that var is empty or the pool fails. **A memory fallback means campaigns do not survive restarts** — check logs for `langgraph_checkpointer_memory_fallback` when resume behavior looks broken.
- `NEON_DATABASE_URL` is separate from `DATABASE_URL` because the checkpointer uses psycopg (sync-style DSN) while the app uses SQLAlchemy asyncpg. `_normalize_psycopg_conninfo` strips the `postgresql+asyncpg://` prefix.
- Shared state shape is `CampaignState` in [state.py](backend/src/agency/agents/state.py). Adding a field there affects every node.
- `autonomous_operator.py`, `competitive_intel.py`, and `video_script.py` are separate entry points, not nodes in the main graph.

### LLM routing (`services/llm_provider.py`)

Three tiers, provider-agnostic. Agents only ever call `get_brain_llm()`, `get_worker_llm(temperature)`, or `get_ad_copy_llm()` — keep it that way when adding agents.

| Tier | Used by | Temperature |
|---|---|---|
| `brain` | Orchestrator, QA/Brand | 0.3 |
| `worker` | Strategy, SEO, Content | 0.7 |
| `ad_copy` | Ad Copy | 0.8 |

Six providers are supported: `anthropic` and `google` via their native SDKs, and `openai`, `nvidia`, `openrouter`, `bonsai` as OpenAI-compatible endpoints through `ChatOpenAI(base_url=...)`. **A blank API key disables a provider** — adding a key is the whole activation step.

Per tier, the first provider in `LLM_PROVIDER_ORDER` (default `anthropic,google,openai,nvidia,openrouter,bonsai`) with a key becomes primary, and the rest attach as LangChain `.with_fallbacks()` — free-tier gateways return transient 503s under load, so a second key keeps a campaign alive. `LLM_{TIER}_PROVIDER` pins a tier to one provider and **disables its fallbacks** (pinning means "use exactly this"). `LLM_{TIER}_MODEL` overrides the model for the primary only — model ids are provider-specific, so forwarding one to a fallback would guarantee it fails.

If no provider is configured, `get_llm()` raises naming the variables to set. Do not restore a silent default: the previous code built a client with an empty key, which killed the pipeline inside the first agent and left campaigns stuck in `running` with no diagnostic.

`GET /api/v1/health/llm` (authenticated) reports the resolved provider, model, and fallback chain per tier without exposing key material.

### Auth & tenant isolation

Dual-mode by design — do not collapse it:

1. **Clerk** (production): when both `CLERK_JWKS_URL` and `CLERK_SECRET_KEY` are set, `get_current_user` verifies the RS256 JWT against cached JWKS, then **auto-provisions** an `Organization` + `User` + free `Subscription` on first sign-in ([dependencies.py](backend/src/agency/dependencies.py)). `DEMO_ORG_ID` + `DEMO_ORG_ALLOWLIST` route allowlisted emails into the seeded demo org instead.
2. **Local HS256 JWT** (dev/CI/tests): falls back to `POST /api/v1/auth/login` against seeded users in `db/seed.sql`.

`TenantMiddleware` decodes `org_id` from the bearer token into `request.state.org_id`; `get_org_id` prefers that over the token payload. **Every org-scoped query must filter on `org_id`** — there is no row-level security in the database. `ApiKeyAuthMiddleware` handles the `X-API-Key` path for `routers/public_api.py`.

Frontend auth: [middleware.ts](frontend/middleware.ts) marks only `/`, `/sign-in`, `/sign-up`, and `/api/webhooks/*` public. `ClerkTokenSync` calls `setClerkTokenGetter()` once so [lib/api.ts](frontend/src/lib/api.ts) can attach `Authorization` headers — the API client has no direct Clerk dependency.

### Real-time streaming

Agent progress streams over **SSE**, not WebSocket, despite `docs/features/websocket.md`. `GET /api/v1/campaigns/{id}/stream?token=...` passes the JWT as a **query param** because `EventSource` cannot set headers ([lib/agent-stream.ts](frontend/src/lib/agent-stream.ts)). The client closes the stream on `complete` or `error` events.

### Product analytics

`product_event` + [services/product_analytics.py](backend/src/agency/services/product_analytics.py) back `GET /api/v1/beta-metrics`. Two rules when extending it:

- **Only `CLIENT_WRITABLE_EVENTS` may come from the browser.** Pipeline and error events are server-authored so a client cannot inflate completion or failure counts. `POST /api/v1/events` silently rejects anything else.
- **`AGENT_FUNNEL_ORDER` must match the graph's node names** — a test asserts this, because a drifted funnel silently reports fake drop-off.

`track()` joins the caller's session (caller commits); `track_detached()` opens its own and never raises. `RequestMetricsMiddleware` keeps request totals in memory (resets on restart) and persists only 4xx/5xx.

To make a new flow show up in the adoption table, call `trackFeature("kebab-name")` from the frontend at the point of success.

### Backend layering

`routers/` (23 routers, all mounted under `/api/v1`) → `services/` (21 modules: billing, publishing, scheduler, brand_learning, cross_learning, white_label, webhook_dispatcher, …) → `models/` (`tables.py` SQLAlchemy, `schemas.py` Pydantic, `database.py` session factory). Keep business logic in `services/`; routers stay thin.

`main.py` registers a background `scheduler` on startup alongside the graph runtime — both need matching shutdown handling.

### Database

Schema is raw SQL in [db/init.sql](db/init.sql) (+ `db/seed.sql`), **not** Alembic migrations, even though `alembic` is a dependency. Schema changes must be applied to both `db/init.sql` and `models/tables.py`.

### CORS

`CORS_ORIGINS` accepts either a JSON array string or a comma-separated string (`_parse_cors_origins` in `main.py`).

## Marketing Agency Layer

Marketing assets live under **`.cursor/`** (there is no `.claude/` directory in this repo):

| Path | Contents |
|---|---|
| `.cursor/workflows/` | `primary-workflow.md`, `sales-workflow.md`, `crm-workflow.md`, `marketing-rules.md`, `orchestration-protocol.md`, `documentation-management.md`, `data-reliability-rules.md` |
| `.cursor/agents/` | 20 marketing agents (attraction-specialist, lead-qualifier, email-wizard, copywriter, seo-specialist, reviewer personas, …) |
| `.cursor/skills/` | 70+ skills. The `agency-*` skills (`agency-backend`, `agency-frontend`, `agency-database`, `agency-ai-engine`, `agency-deploy`, `agency-testing`, `agency-billing`, `agency-realtime`, `agency-agentmail`, `agency-project`) document **this codebase** — read the relevant one before non-trivial product work |
| `.cursor/commands/` | 93 slash commands grouped by domain (campaign, content, seo, cro, growth, analytics, …) |
| `campaigns/` | Campaign outputs (e.g. `ai-upskill-cohort`) |

When doing marketing work: read `README.md` for context, follow `.cursor/workflows/marketing-rules.md`, and activate relevant skills from `.cursor/skills/`.

**CRITICAL — data reliability:** never fabricate metrics. Use MCP integrations for real data; if unavailable, output "⚠️ NOT AVAILABLE" with setup instructions. Full rules in `.cursor/workflows/data-reliability-rules.md`.

Reporting style: sacrifice grammar for concision; list unresolved questions at the end.

## Documentation

`docs/features/` holds living feature docs (API endpoints, database schema, services, frontend pages, auth/RBAC, billing, changelog). After adding, modifying, or removing a feature, refresh them via the `feature-docs` skill. `docs/beta-testing-plan.md` defines the beta program; `docs/yc-pitch.md` the investor narrative.

Known drift to watch for: `docs/features/websocket.md` describes the realtime layer as WebSocket, but the implementation is SSE.
