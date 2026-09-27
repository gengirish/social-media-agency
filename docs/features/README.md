# Feature Documentation
<!-- verified: 260923 -->

Living documentation of all platform features. Updated whenever the codebase changes.

## Quick Stats
- **API Endpoints**: 133 across 35 routers (all mounted under `/api/v1`) — 260923 added 10 routers / 42 endpoints
- **Database Tables**: 24 (`creative_asset`, `inbox_item_state` added 260923)
- **Services**: 44 modules in `services/`
- **Background Workers**: 3 asyncio tasks (no Celery; there is no `workers/` package)
- **Frontend Pages**: 26 `page.tsx` files
- **Frontend Components**: 15 `ui/` primitive files + feature folders (`layout/`, `posts/`, `amplify/`, `clients/`, `setup/`, `create-content/`, `create-kits/`, `ads/`, `inbox/`, `insights/`, `settings/`, `agents/`, `landing/`) + app-level components; lib modules incl. 8 per-feature `api-*.ts` wrappers and `active-client.tsx`
- **Platform Integrations**: 8 (Clerk, Stripe, AgentMail, Social publishing + Inbox reading, LLM, fal.ai, Slack, Exa)
- **LangGraph Nodes**: 9 (7 LLM agents + `human_review` + `compile_output`)
- **Agent Modules**: 19 (7 graph agents + 12 standalone: `autonomous_operator`, `competitive_intel`, `video_script`, `amplify`, and 260923's `post_writer`, `setup_profile`, `create_content`, `lifecycle_email`, `launch_pr`, `ads`, `advocacy`, `inbox_reply`)

> **Before deploying `feat/cadence-parity`:** run `db/migrations/260923_creative_asset.sql`, then `260923_amplify_asset_source.sql`, then `260923_inbox.sql` by hand on Neon ([database-schema.md](database-schema.md#database-schema)). New optional env vars: `LINKEDIN_INBOX_SCOPE` (blank until the LinkedIn app is approved for comment reading), `LINKEDIN_API_VERSION` (default `202608`) — both in `.env.example` / `backend/.env.example`.

## Documents

| Document | Description | Last Updated |
|----------|-------------|-------------|
| [api-endpoints.md](api-endpoints.md) | All 133 REST API endpoints, approval gate, Amplify, generator contract, Setup, Post Studio, Create, Inbox, Insights, Workspace, OAuth | 260923 |
| [database-schema.md](database-schema.md) | 24 tables, columns, relationships, pending Neon migrations | 260923 |
| [services.md](services.md) | Business logic services, moderation, shared generator services, inbox, insights | 260923 |
| [workers.md](workers.md) | Asyncio background tasks | 260817 |
| [integrations.md](integrations.md) | Social publishing + Inbox reading, Stripe, Clerk, AgentMail, LLM, fal.ai, Slack, Exa | 260923 |
| [websocket.md](websocket.md) | SSE real-time agent streaming (no WebSocket) | 260921 |
| [frontend-pages.md](frontend-pages.md) | 26 UI pages, top-nav IA + shortcuts, active client, Welcome, Setup, Create, Queue/Calendar, Inbox, Insights, Settings | 260923 |
| [frontend-components.md](frontend-components.md) | Design system, `ui/` primitives, shell, feature components, lib + `api-*` modules | 260923 |
| [auth-and-rbac.md](auth-and-rbac.md) | Clerk + legacy JWT, roles, multi-tenancy, portal, OAuth state | 260923 |
| [billing.md](billing.md) | Stripe billing, 4 plan tiers, shared generation quota | 260923 |
| [changelog.md](changelog.md) | Chronological change log | 260923 |

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
| Audit log | `services/audit.py` | Only Inbox replies call `log_action` (260923); nothing else is audited | `GET /audit` returns `status: unavailable` when empty (its reason text, "no route writes audit entries", is now stale) |
| LinkedIn Inbox | `services/inbox.py` | Needs a restricted LinkedIn permission; off unless `LINKEDIN_INBOX_SCOPE` is set | Per-account `api_access_denied` banner with LinkedIn's requirement spelled out |
| DMs | `services/inbox.py` | Not read on any platform | DM chip marked unavailable with the reason |
| X Inbox reads | `services/inbox.py` | Depend on the X API plan (pay-per-use reads) | X's own 402/403 text shown as `api_access_denied` |
| Ad accounts / spend / CTR | `routers/create_ads.py` | Copy and structure only | Prominent notice on `/create/ads` |
| Email sending, launch submission | `create_email.py`, `create_launch.py` | Drafts only | Screens say so; no send/submit button |
| OAuth account handle | `routers/oauth.py` | Stored as the placeholder `{platform}_user` | Not flagged in the UI |
| RBAC enforcement | `services/team.py` | `check_permission` has no callers | Team page carries an amber banner saying roles are labels, not restrictions |
| `performance_score` | never written | No producer | `GET /content/suggestions` returns `status: unavailable` |
| Org logo upload | no endpoint | Not implemented | Settings shows "Logo upload not available yet" |
| Slack campaign creation | `routers/slack.py` | No pipeline is started | `/campaignforge create` replies that it is unavailable |
| Analytics agent insights | `agents/analytics.py` | Needs published + measured content | Returns `status: unavailable` with a reason instead of calling the LLM on `{}` |
| Amplify output quality | `agents/amplify.py` | Validated structurally (angles, limits, duplicates); not yet reviewed on real generations | Nothing reaches the queue until a human keeps it; every draft still needs moderated approval |

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│  Frontend (Next.js 15 + React 19 + Clerk)            │
│  Vercel · 26 pages · Tailwind tokens, light/dark     │
└────────────────────┬────────────────────────────────┘
                     │ HTTPS + SSE
┌────────────────────▼────────────────────────────────┐
│  Backend (FastAPI)                                   │
│  Fly.io · 133 endpoints · 35 routers                 │
│  Clerk JWT + HS256 fallback + X-API-Key              │
├──────────────────────────────────────────────────────┤
│  LangGraph Agent Pipeline (9 nodes)                  │
│  Orchestrator → [Strategy ∥ SEO] → [Content ∥ Ads]   │
│  → Human Review → QA/Brand → Compile → Analytics     │
├──────────────────────────────────────────────────────┤
│  Services: 44 modules — Billing · Publishing · Scheduler · LLM   │
│  Moderation · Approval gate · Quota · Brand context · Inbox · …  │
└────────────────────┬────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────┐
│  PostgreSQL (Neon) · 24 tables · Multi-tenant        │
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
