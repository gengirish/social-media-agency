# Feature Documentation
<!-- verified: 260817 -->

Living documentation of all platform features. Updated whenever the codebase changes.

## Quick Stats
- **API Endpoints**: 82 across 24 routers (all mounted under `/api/v1`)
- **Database Tables**: 18
- **Services**: 23 modules in `services/`
- **Background Workers**: 3 asyncio tasks (no Celery; there is no `workers/` package)
- **Frontend Pages**: 17 `page.tsx` files
- **Frontend Components**: 5 reusable + 4 lib modules
- **Platform Integrations**: 7 (Clerk, Stripe, AgentMail, Social publishing, LLM, fal.ai, Slack)
- **LangGraph Nodes**: 9 (7 LLM agents + `human_review` + `compile_output`)
- **Agent Modules**: 10 (7 graph agents + 3 standalone entry points)

## Documents

| Document | Description | Last Updated |
|----------|-------------|-------------|
| [api-endpoints.md](api-endpoints.md) | All 82 REST API endpoints | 260817 |
| [database-schema.md](database-schema.md) | 18 tables, columns, relationships | 260817 |
| [services.md](services.md) | 23 business logic services | 260817 |
| [workers.md](workers.md) | Asyncio background tasks | 260817 |
| [integrations.md](integrations.md) | Social, Stripe, Clerk, AgentMail, LLM, fal.ai, Slack | 260817 |
| [websocket.md](websocket.md) | SSE real-time agent streaming | 260817 |
| [frontend-pages.md](frontend-pages.md) | 17 UI pages and routes | 260817 |
| [frontend-components.md](frontend-components.md) | Reusable components + lib modules | 260817 |
| [auth-and-rbac.md](auth-and-rbac.md) | Clerk + legacy JWT, roles, multi-tenancy | 260817 |
| [billing.md](billing.md) | Stripe billing, 4 plan tiers | 260817 |
| [changelog.md](changelog.md) | Chronological change log | 260817 |

## Feature Honesty

Everything below is either **real** or **visibly marked unavailable in the UI**. Nothing "looks real but isn't". Full evidence: [stub-audit-260817.md](../stub-audit-260817.md).

Fixed in Phase 1 (no longer stubs): analytics metrics (`analytics_fetcher.py` now calls real platform APIs, `NULL` not `0`), trending topics (`trends.py` via Exa), RAG (`knowledge_base.py` real cosine similarity + `retrieval_mode` label), webhooks (DB-backed + HMAC), competitive intel (source-URL gated).

Remaining gaps — all surfaced honestly to the user:

| Feature | Where | Reality | How the user is told |
|---------|-------|---------|----------------------|
| Instagram publishing | `services/publishing.py` (T2.1) | Not implemented | Publish button replaced by "Publishing unavailable" badge; API returns `success: false` |
| TikTok publishing | no publisher exists | Not implemented | "draft only" badge on channel picker and repurpose targets |
| Instagram metrics | `services/platform_metrics.py` (T2.2) | Returns `unavailable` | Content analytics shows the unavailable reason |
| Notifications | `services/notifications.py` | `create_notification` has no callers | Bell says notifications are not generated yet; Settings → Notifications shows "Not available yet" |
| Audit log | `services/audit.py` | `log_action` has no callers | `GET /audit` returns `status: unavailable` with a reason |
| RBAC enforcement | `services/team.py` | `check_permission` has no callers | Team page carries an amber banner saying roles are labels, not restrictions |
| `performance_score` | never written | No producer | `GET /content/suggestions` returns `status: unavailable` |
| Org logo upload | no endpoint | Not implemented | Settings shows "Logo upload not available yet" |
| Slack campaign creation | `routers/slack.py` | No pipeline is started | `/campaignforge create` replies that it is unavailable |
| Analytics agent insights | `agents/analytics.py` | Needs published + measured content | Returns `status: unavailable` with a reason instead of calling the LLM on `{}` |

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│  Frontend (Next.js 15 + React 19 + Clerk)            │
│  Vercel · 17 pages · Tailwind + Inter                │
└────────────────────┬────────────────────────────────┘
                     │ HTTPS + SSE
┌────────────────────▼────────────────────────────────┐
│  Backend (FastAPI)                                   │
│  Fly.io · 82 endpoints · 24 routers                  │
│  Clerk JWT + HS256 fallback + X-API-Key              │
├──────────────────────────────────────────────────────┤
│  LangGraph Agent Pipeline (9 nodes)                  │
│  Orchestrator → [Strategy ∥ SEO] → [Content ∥ Ads]   │
│  → Human Review → QA/Brand → Compile → Analytics     │
├──────────────────────────────────────────────────────┤
│  Services: 23 modules — Billing · Publishing · Scheduler · LLM   │
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
| `[STUB]` | Route/UI exists but returns placeholder or hardcoded data — do not sell |
| `[PLANNED]` | Feature is designed but not yet built |
| `[DEPRECATED]` | Feature is scheduled for removal |
