# Feature Documentation
<!-- verified: 260324 -->

Living documentation of all platform features. Updated whenever the codebase changes.

## Quick Stats
- **API Endpoints**: 36 across 10 routers
- **Database Tables**: 15
- **Services**: 8
- **Background Workers**: 3 (asyncio-based, no Celery)
- **Frontend Pages**: 15
- **Frontend Components**: 3 reusable
- **Platform Integrations**: 5 (Clerk, Stripe, AgentMail, Social, LLM)
- **LangGraph Agent Nodes**: 8

## Documents

| Document | Description | Last Updated |
|----------|-------------|-------------|
| [api-endpoints.md](api-endpoints.md) | All 36 REST API endpoints | 260324 |
| [database-schema.md](database-schema.md) | 15 tables, columns, relationships | 260324 |
| [services.md](services.md) | 8 business logic services | 260324 |
| [workers.md](workers.md) | Asyncio background tasks | 260324 |
| [integrations.md](integrations.md) | Social, Stripe, Clerk, AgentMail, LLM | 260324 |
| [websocket.md](websocket.md) | SSE real-time agent streaming | 260324 |
| [frontend-pages.md](frontend-pages.md) | 15 UI pages and routes | 260324 |
| [frontend-components.md](frontend-components.md) | Reusable components + lib modules | 260324 |
| [auth-and-rbac.md](auth-and-rbac.md) | Clerk + legacy JWT, roles, multi-tenancy | 260324 |
| [billing.md](billing.md) | Stripe billing, 4 plan tiers | 260324 |
| [changelog.md](changelog.md) | Chronological change log | 260324 |

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│  Frontend (Next.js 14 + Clerk)                       │
│  Vercel Edge · 15 pages · Tailwind + Inter           │
└────────────────────┬────────────────────────────────┘
                     │ HTTPS + SSE
┌────────────────────▼────────────────────────────────┐
│  Backend (FastAPI)                                    │
│  Fly.io · 36 endpoints · Clerk JWT + HS256 fallback  │
├──────────────────────────────────────────────────────┤
│  LangGraph Agent Pipeline                            │
│  Orchestrator → [Strategy ∥ SEO] → [Content ∥ Ads]  │
│  → Human Review → QA/Brand → Output                 │
├──────────────────────────────────────────────────────┤
│  Services: Billing · Publishing · Scheduler · LLM    │
│  Brand Learning · Magic Brief · Team · API Keys      │
└────────────────────┬────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────┐
│  PostgreSQL (Neon) · 15 tables · Multi-tenant        │
└─────────────────────────────────────────────────────┘
```

## How This Works

These docs are maintained by the **`feature-docs`** skill (`.cursor/skills/feature-docs/`). The skill:

1. Scans source code for routers, models, services, pages, etc.
2. Compares against what's documented here
3. Updates the matching doc file with current state
4. Appends changes to the changelog

### Keeping Docs Current

After any code change that adds, modifies, or removes a feature:
- Ask the agent to "update feature docs" or reference the `feature-docs` skill
- The skill will detect what changed and update only the relevant files

### Status Labels

| Label | Meaning |
|-------|---------|
| `[LIVE]` | Feature is implemented and active |
| `[IN PROGRESS]` | Feature is partially implemented |
| `[PLANNED]` | Feature is designed but not yet built |
| `[DEPRECATED]` | Feature is scheduled for removal |
