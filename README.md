# CampaignForge AI

**Replace your marketing agency with 7 AI agents.** One brief, complete campaign, 5 minutes, $49/month.

## What It Is

CampaignForge is a multi-agent AI marketing platform that runs an entire campaign pipeline — strategy, SEO, content, ad copy, QA — through specialized LangGraph agents with human-in-the-loop review.

## Tech Stack

| Layer | Technology | Hosting |
|-------|-----------|---------|
| Frontend | Next.js 14 + Tailwind + Clerk | Vercel |
| Backend | FastAPI + LangGraph | Fly.io |
| Database | PostgreSQL (Neon serverless) | Neon |
| AI Brain | Claude Sonnet (orchestrator/QA) | Anthropic |
| AI Workers | Gemini 2.0 Flash (content) | Google |
| Payments | Stripe subscriptions | — |
| Email | AgentMail | — |

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
| `DATABASE_URL` | PostgreSQL connection string |
| `CLERK_SECRET_KEY` | Clerk Backend API key |
| `CLERK_JWKS_URL` | Clerk JWKS endpoint |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | Clerk frontend key |
| `GOOGLE_API_KEY` | Gemini (worker LLM) |
| `ANTHROPIC_API_KEY` | Claude (brain LLM) |
| `STRIPE_SECRET_KEY` | Billing |

## Architecture

```
Brief → Orchestrator → [Strategy ∥ SEO] → [Content ∥ Ads] → Human Review → QA → Publish
```

7 specialized agents run in parallel where possible. The pipeline uses LangGraph with `interrupt_before` for human review. SSE streams agent progress to the frontend in real time.

## Project Structure

```
backend/
  src/agency/
    agents/       # 8 LangGraph nodes (orchestrator, strategy, SEO, content, ads, QA, analytics, review)
    routers/      # 10 FastAPI routers (36 endpoints)
    services/     # 8 services (billing, publishing, scheduler, LLM, brand learning, etc.)
    models/       # SQLAlchemy models (15 tables) + Pydantic schemas
    middleware/    # Tenant isolation middleware
frontend/
  src/
    app/          # 15 Next.js pages (campaigns, clients, content, analytics, settings, etc.)
    components/   # LiveAgentDashboard, DashboardContent, ClerkTokenSync
    lib/          # API client, SSE stream, utils
docs/
  features/       # Living feature documentation (auto-updated)
```

## Feature Documentation

See [`docs/features/`](docs/features/README.md) for comprehensive, auto-maintained docs covering all API endpoints, database schema, services, frontend pages, auth flow, and billing.

## AI Skills Hub

This workspace includes 70+ specialized marketing skills, 20 agents, and 93 slash commands for Cursor IDE:

- **AgentKits Marketing Kit** — 28 skills, 20 agents, 93 commands ([source](https://github.com/aitytech/agentkits-marketing))
- **Marketing Skills Library** — 160+ skills for SEO, content, ads, growth ([source](https://github.com/kostja94/marketing-skills))
- **Individual Skills** — crosspost, deep-research, investor-materials, typefully, and more

## License

Skills are sourced from open-source MIT-licensed repositories.
