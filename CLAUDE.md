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

Backend config lives in [backend/fly.toml](backend/fly.toml) — note `internal_port = 8080` (the container listens on 8080; local dev uses 8001).

**`CORS_ORIGINS` is the highest-consequence backend env var, and its ORDER matters.** A missing origin is invisible from the server side: Starlette answers a disallowed preflight with a bare `400` and logs nothing, so the API looks healthy while every browser request fails — and `curl` keeps working, because curl does not preflight. On 260818 the canonical domain was absent from it in production and the entire app was unusable in a browser. The **first** entry is separately treated as the app's own base URL when building OAuth redirect URIs (`routers/oauth.py::_first_cors_origin`), so a wrong first entry silently breaks every OAuth callback. `main.py` logs the resolved list as `cors_allowed_origins` at startup — check `fly logs` for it before debugging a CORS report.

### Deploying

CI is [.github/workflows/ci.yml](.github/workflows/ci.yml) (backend lint/type/test, frontend lint/build, E2E). There is **no deploy job**.

- **Backend:** `fly deploy` from `backend/`. `flyctl secrets set` also redeploys on its own.
- **Frontend:** Vercel project `campaignforge-ai` (Root Directory `frontend`), deployed by Git integration on push to `main`.

The Vercel project's **Root Directory is `frontend`**, which makes CLI deploys counter-intuitive: running `vercel --prod` from inside `frontend/` fails with `frontendrontend does not exist`, because the setting is applied on top of your cwd. Deploy from the **repo root** instead, and pass `--archive=tgz` or the upload trips the 15,000-file cap on this repo:

```bash
npx vercel --prod --archive=tgz   # from the repo ROOT, not frontend/
```

[frontend/vercel.json](frontend/vercel.json) still patches a missing `page_client-reference-manifest.js` after `next build`. It is probably now **vestigial**: it was papering over an intermittent `InvariantError: Expected clientReferenceManifest` whose real cause was two pages resolving to `/` (`app/page.tsx` and a dead `app/(dashboard)/page.tsx`), fixed on 260818. The hack could never have helped anyway — it runs *after* `next build` returns, so a build that dies during prerender never reaches it. Removing it is safe to try, but verify a few consecutive clean builds first; the failure it masked was intermittent (~1 in 4), so a single green build proves nothing.

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

**Four** tiers, provider-agnostic. Agents only ever call `get_brain_llm()`, `get_worker_llm(temperature)`, `get_ad_copy_llm()`, or `get_lite_llm(temperature)` — keep it that way when adding agents.

| Tier | Used by | Temperature |
|---|---|---|
| `brain` | Orchestrator, QA/Brand | 0.3 |
| `worker` | Strategy, SEO, Content | 0.7 |
| `ad_copy` | Ad Copy | 0.8 |
| `lite` | SEO keyword extraction, content repurposing, A/B variants | caller-set |

`lite` is for work that **transforms text it is handed rather than deciding anything**. Do not reach for it where campaign quality depends on the judgement in the output — that is what `worker` and `brain` are for.

**Seven** providers are supported: `anthropic` and `google` via their native SDKs, and `openai`, `nvidia`, `openrouter`, `bonsai`, `groq` as OpenAI-compatible endpoints through `ChatOpenAI(base_url=...)`. **A blank API key disables a provider** — adding a key is the whole activation step.

Adding a provider takes **two** edits, not one: a `ProviderSpec` in `_provider_specs()` **and** its name in `DEFAULT_PROVIDER_ORDER`. `_configured_order()` filters against that tuple, so a provider with settings and a spec but no entry there is dropped from the order silently — no error, no log, it simply never gets picked. (Groq's base URL is also `https://api.groq.com/openai/v1`, not `/v1`; the usual shape 404s every call.)

Per tier, the first provider in `LLM_PROVIDER_ORDER` (default `anthropic,google,openai,nvidia,openrouter,bonsai,groq`) with a key becomes primary, and the rest attach as LangChain `.with_fallbacks()` — free-tier gateways return transient 503s under load, so a second key keeps a campaign alive. `LLM_{TIER}_PROVIDER` pins a tier to one provider and **disables its fallbacks** (pinning means "use exactly this"). `LLM_{TIER}_MODEL` overrides the model for the primary only — model ids are provider-specific, so forwarding one to a fallback would guarantee it fails.

If no provider is configured, `get_llm()` raises naming the variables to set. Do not restore a silent default: the previous code built a client with an empty key, which killed the pipeline inside the first agent and left campaigns stuck in `running` with no diagnostic.

`GET /api/v1/health/llm` (authenticated) reports the resolved provider, model, and fallback chain per tier without exposing key material.

### Auth & tenant isolation

Dual-mode by design — do not collapse it:

1. **Clerk** (production): when both `CLERK_JWKS_URL` and `CLERK_SECRET_KEY` are set, `get_current_user` verifies the RS256 JWT against cached JWKS, then **auto-provisions** an `Organization` + `User` + free `Subscription` on first sign-in ([dependencies.py](backend/src/agency/dependencies.py)). `DEMO_ORG_ID` + `DEMO_ORG_ALLOWLIST` route allowlisted emails into the seeded demo org instead.
2. **Local HS256 JWT** (dev/CI/tests): falls back to `POST /api/v1/auth/login` against seeded users in `db/seed.sql`.

`TenantMiddleware` decodes `org_id` from the bearer token into `request.state.org_id`; `get_org_id` prefers that over the token payload. **Every org-scoped query must filter on `org_id`** — there is no row-level security in the database. `ApiKeyAuthMiddleware` handles the `X-API-Key` path for `routers/public_api.py`.

Two rules that follow from having no RLS, both of which were violated in shipped code before 260817:

- **Any id that arrives from the client — path param, body field, query string — must be resolved against `org_id` before it is written to or joined on.** A `client_id` taken from a request body and trusted (`routers/oauth.py`) let one tenant attach a connected social account to another tenant's client, which `publish_now` then selected because *its* lookup was also unscoped. Neither gap was exploitable alone.
- `get_current_user` returns the **JWT payload dict** in both auth modes, never an ORM `User`. Use `get_current_user_id` for the caller's id; `user.id` raises `AttributeError` and surfaces as a 500.

`backend/tests/test_tenancy_routers.py` covers these per router, and every test in it is verified to fail when its filter is deleted — keep that property when adding more.

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

`routers/` (24 routers, all mounted under `/api/v1`) → `services/` (24 modules: billing, publishing, scheduler, brand_learning, cross_learning, white_label, webhook_dispatcher, platform_metrics, exa_client, …) → `models/` (`tables.py` SQLAlchemy, `schemas.py` Pydantic, `database.py` session factory). Keep business logic in `services/`; routers stay thin.

`main.py` registers a background `scheduler` on startup alongside the graph runtime — both need matching shutdown handling.

### Database

Schema is raw SQL in [db/init.sql](db/init.sql) (+ `db/seed.sql`), **not** Alembic migrations, even though `alembic` is a dependency. Schema changes must be applied to both `db/init.sql` and `models/tables.py`.

`init.sql` only runs on a **fresh** database, so a schema change is invisible to any already-provisioned environment (Neon prod, a local volume that was not reset). Alongside the two edits above, add a dated forward-only script to [db/migrations/](db/migrations/) — e.g. [260817_org_slug.sql](db/migrations/260817_org_slug.sql) — and run it by hand on Neon. Nothing applies these automatically.

`organization.slug` is the portal's identity column and is `UNIQUE` deliberately: `/api/v1/portal/{org_slug}` is unauthenticated, and the previous `domain`-then-`name` resolution used non-unique columns. A null slug means that org has no portal.

### CORS

`CORS_ORIGINS` accepts either a JSON array string or a comma-separated string (`_parse_cors_origins` in `main.py`).

## Marketing Agency Layer

Marketing assets are mirrored in **two trees**: `.claude/` (what Claude Code loads) and `.cursor/` (what Cursor loads). They are byte-identical apart from `.claude/settings.local.json`, which is gitignored.

**Edit both, or they drift.** Nothing syncs them automatically. Treat `.claude/` as the source of truth, port the change across, and confirm with `diff -rq .cursor .claude` — the only expected output is `Only in .claude: settings.local.json`.

| Path (under `.claude/`, mirrored in `.cursor/`) | Contents |
|---|---|
| `workflows/` | `primary-workflow.md`, `sales-workflow.md`, `crm-workflow.md`, `marketing-rules.md`, `orchestration-protocol.md`, `documentation-management.md`, `data-reliability-rules.md` |
| `agents/` | 20 marketing agents (attraction-specialist, lead-qualifier, email-wizard, copywriter, seo-specialist, reviewer personas, …) |
| `skills/` | 59 skills. The `agency-*` skills (`agency-backend`, `agency-frontend`, `agency-database`, `agency-ai-engine`, `agency-deploy`, `agency-testing`, `agency-billing`, `agency-realtime`, `agency-agentmail`, `agency-project`) document **this codebase** — read the relevant one before non-trivial product work |
| `commands/` | 100 slash commands grouped by domain (campaign, content, seo, cro, growth, analytics, …) plus the English `training/` course |
| `rules/deployment-domains.mdc` | Cursor `.mdc` rule format; Claude Code does not read `.claude/rules/`, so this file is inert on the Claude side |
| `campaigns/` (repo root) | Campaign outputs (e.g. `ai-upskill-cohort`) |

`.claude/settings.local.json` is gitignored — machine-local permissions, do not commit it.

MCP setup: Claude Code reads `.mcp.json` at the **repository root**, not `.claude/mcp.json`. Start from `.claude/mcp.json.example`, which lists only servers that actually exist; providers with no MCP server are enumerated under `_no_mcp_server_available` with the API to call instead.

When doing marketing work: read `README.md` for context, follow `.claude/workflows/marketing-rules.md`, and activate relevant skills from `.claude/skills/`.

**CRITICAL — data reliability:** never fabricate metrics. Use MCP integrations for real data; if unavailable, output "⚠️ NOT AVAILABLE" with setup instructions. Full rules in `.claude/workflows/data-reliability-rules.md`.

Reporting style: sacrifice grammar for concision; list unresolved questions at the end.

## Documentation

`docs/features/` holds living feature docs (API endpoints, database schema, services, frontend pages, auth/RBAC, billing, changelog). After adding, modifying, or removing a feature, refresh them via the `feature-docs` skill. `docs/beta-testing-plan.md` defines the beta program; `docs/yc-pitch.md` the investor narrative.

Known drift to watch for: `docs/features/websocket.md` describes the realtime layer as WebSocket, but the implementation is SSE.
