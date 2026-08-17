# CampaignForge AI

**Take on more clients without hiring.** Brief in, client-ready campaign out — strategy, SEO, copy and brand QA in one pass, under your logo.

## What It Is

CampaignForge is a multi-agent AI marketing platform that runs an entire campaign pipeline — strategy, SEO, content, ad copy, QA — through specialized LangGraph agents with human-in-the-loop review.

Positioning as of 260817: the ICP is **small agencies and freelancers managing 3–15 client brands**, sold on white-label output and the human review gate. The earlier "replace your marketing agency for $49" line targeted the buyer this product is built to serve, and collided verbatim with a YC-funded competitor's tagline — see [docs/competitive-analysis-gtm.md](docs/competitive-analysis-gtm.md).

## Tech Stack

| Layer | Technology | Hosting |
|-------|-----------|---------|
| Frontend | Next.js 15 + React 19 + Tailwind + Clerk | Vercel |
| Backend | FastAPI + LangGraph | Fly.io |
| Database | PostgreSQL (Neon serverless) | Neon |
| AI Brain | Claude Sonnet (orchestrator/QA) | Anthropic |
| AI Workers | Gemini 2.5 Flash (strategy/SEO/content) | Google |
| LLM failover | 6 providers, per-tier fallback chain | Anthropic · Google · OpenAI · NVIDIA · OpenRouter · Bonsai |
| Payments | Stripe subscriptions | — |
| Email | AgentMail | — |
| Images | fal.ai (flux/schnell) | — |

### Live URLs

| Environment | URL |
|-------------|-----|
| Frontend | `https://campaignforge.intelliforge.tech` |
| Backend API | `https://campaignforge-api.fly.dev` |

## Quick Start

### Prerequisites
- Python 3.12+, Node.js 18+, PostgreSQL (or Neon)

### Backend
```bash
cd backend
cp .env.example .env   # fill in API keys
pip install -e .
uvicorn agency.main:app --reload --port 8001
```

### Frontend
```bash
cd frontend
cp .env.example .env.local   # fill in Clerk keys + API URL
npm install
npm run dev
```

### Required Environment Variables

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | PostgreSQL connection string (SQLAlchemy asyncpg) |
| `NEON_DATABASE_URL` | **Separate** DSN for the LangGraph checkpointer (psycopg sync-style). If empty, checkpointing silently falls back to in-memory and campaigns do not survive restarts |
| `CLERK_SECRET_KEY` | Clerk Backend API key |
| `CLERK_JWKS_URL` | Clerk JWKS endpoint |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | Clerk frontend key |
| `GOOGLE_API_KEY` | Gemini (worker LLM); `GEMINI_API_KEY` accepted as alias |
| `ANTHROPIC_API_KEY` | Claude (brain LLM) |
| `STRIPE_SECRET_KEY` | Billing |
| `STRIPE_WEBHOOK_SECRET` | Webhook signature verification; the endpoint returns 503 without it |

At least one LLM provider key is required — with none set, `get_llm()` raises immediately naming the variables to set.

## Architecture

```
Brief → Orchestrator → [Strategy ∥ SEO] → [Content ∥ Ads]
      → Human Review → QA/Brand → Compile → Analytics
```

7 specialized LLM agents across 9 LangGraph nodes, running in parallel where possible. The graph compiles with `interrupt_before=["human_review"]`, so execution **pauses** there and resumes when a decision lands via `PATCH /api/v1/campaigns/{id}/review`. A conditional router loops critical QA failures back to Content or Ad Copy, capped at 2 retries. SSE streams agent progress to the frontend in real time.

## Project Structure

```
backend/
  src/agency/
    agents/       # 10 agent modules — 9 LangGraph nodes + 3 standalone entry points
                  #   (autonomous_operator, competitive_intel, video_script)
    routers/      # 24 FastAPI routers (82 endpoints, all under /api/v1)
    services/     # 23 services (billing, publishing, scheduler, LLM, brand learning, …)
    models/       # SQLAlchemy models (18 tables) + Pydantic schemas
    middleware/   # Tenant isolation, API-key auth, request metrics
db/               # Raw SQL schema (init.sql + seed.sql) — NOT Alembic migrations
frontend/
  src/
    app/          # 17 Next.js pages (campaigns, clients, content, analytics, settings, …)
    components/   # LiveAgentDashboard, DashboardContent, ClerkTokenSync,
                  #   NotificationsBell, AnalyticsTracker
    lib/          # API client, SSE stream, analytics, utils
docs/
  features/       # Living feature documentation
```

Schema changes must be applied to **both** `db/init.sql` and `models/tables.py` — there are no migrations despite `alembic` being a dependency.

## Testing

```bash
# Backend
cd backend
ruff check src/ tests/
mypy src/agency/ --ignore-missing-imports
pytest tests/ -v --tb=short

# Frontend
cd frontend
npm run lint && npm run build
npm run test:e2e          # Playwright; needs a running backend
```

CI is [`.github/workflows/ci.yml`](.github/workflows/ci.yml) — backend lint/type/test, frontend lint/build, E2E. There is **no deploy job**; deploys are manual (`fly deploy` from `backend/`, Vercel Git integration for `frontend/`).

## Project Status

Not launch-ready. The agent pipeline, LLM routing, publishing, billing, and multi-tenancy are real and working. Several user-facing features are wired end-to-end but return placeholder data — analytics metrics, trending topics, RAG retrieval, and Instagram publishing. These are labelled `[STUB]` in the feature docs.

Pre-launch work is tracked in [`docs/campaignforge-hardening-backlog.md`](docs/campaignforge-hardening-backlog.md). Do not charge for a feature that is still `[STUB]`.

## Feature Documentation

See [`docs/features/`](docs/features/README.md) for docs covering all API endpoints, database schema, services, frontend pages, auth flow, and billing — including a Feature Honesty table listing exactly which features return placeholder data.

## AI Skills Hub

The repo has a second layer beyond the product: prompt/config assets under `.cursor/` used to *run* marketing work. These are not application code.

| Path | Count |
|------|-------|
| `.cursor/skills/` | 76 skills — the `agency-*` ones document this codebase |
| `.cursor/agents/` | 20 marketing agents |
| `.cursor/commands/` | 330 command files across 34 domain folders |
| `.cursor/workflows/` | 7 workflows (primary, sales, CRM, marketing rules, orchestration, docs, data reliability) |
| `campaigns/` | Campaign outputs |

Sources: [AgentKits Marketing Kit](https://github.com/aitytech/agentkits-marketing), [Marketing Skills Library](https://github.com/kostja94/marketing-skills), plus individual skills (crosspost, deep-research, investor-materials, typefully).

**Data reliability rule:** never fabricate metrics. Use real integrations, or output "⚠️ NOT AVAILABLE" with setup instructions. See `.cursor/workflows/data-reliability-rules.md`.

## License

Skills are sourced from open-source MIT-licensed repositories.
