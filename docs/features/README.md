# Feature Documentation
<!-- verified: 260328 -->

Living documentation of all platform features. Updated whenever the codebase changes.

## Quick Stats
- **API Endpoints**: 86 across 21 routers
- **Database Tables**: 18 (added Notification, AuditLog, ProductEvent)
- **Services**: 21
- **Background Workers**: 3 (asyncio-based, no Celery)
- **Frontend Pages**: 19
- **Frontend Components**: 5 reusable
- **Platform Integrations**: 5 (Clerk, Stripe, AgentMail, Social, LLM)
- **LangGraph Agent Nodes**: 11

## Documents

| Document | Description | Last Updated |
|----------|-------------|-------------|
| [api-endpoints.md](api-endpoints.md) | All 86 REST API endpoints | 260728 |
| [database-schema.md](database-schema.md) | 18 tables, columns, relationships | 260728 |
| [services.md](services.md) | 21 business logic services | 260728 |
| [workers.md](workers.md) | Asyncio background tasks | 260328 |
| [integrations.md](integrations.md) | Social, Stripe, Clerk, AgentMail, LLM | 260328 |
| [websocket.md](websocket.md) | SSE real-time agent streaming | 260328 |
| [frontend-pages.md](frontend-pages.md) | 19 UI pages and routes | 260328 |
| [frontend-components.md](frontend-components.md) | Reusable components + lib modules | 260328 |
| [auth-and-rbac.md](auth-and-rbac.md) | Clerk + legacy JWT, roles, multi-tenancy | 260328 |
| [billing.md](billing.md) | Stripe billing, 4 plan tiers | 260328 |
| [changelog.md](changelog.md) | Chronological change log | 260328 |

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│  Frontend (Next.js 14 + Clerk)                       │
│  Vercel Edge · 19 pages · Tailwind + Inter           │
└────────────────────┬────────────────────────────────┘
                     │ HTTPS + SSE
┌────────────────────▼────────────────────────────────┐
│  Backend (FastAPI)                                    │
│  Fly.io · 86 endpoints · 21 routers · Clerk JWT + HS256 fallback  │
├──────────────────────────────────────────────────────┤
│  LangGraph Agent Pipeline                            │
│  Orchestrator → [Strategy ∥ SEO] → [Content ∥ Ads]  │
│  → Human Review → QA/Brand → Output                 │
├──────────────────────────────────────────────────────┤
│  Services: 21 modules — Billing · Publishing · Scheduler · LLM   │
│  Brand Learning · Magic Brief · Team · API Keys · Reports · …     │
└────────────────────┬────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────┐
│  PostgreSQL (Neon) · 18 tables · Multi-tenant        │
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
