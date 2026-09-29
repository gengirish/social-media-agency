# Feature Documentation
<!-- verified: 260929 -->

Living documentation of all platform features. Updated whenever the codebase changes.

## Quick Stats
- **API Endpoints**: 138 across 35 routers (all mounted under `/api/v1`) — 260923 added 10 routers / 42 endpoints; 260929 added 5 (3 manual-channel routes, `mark-posted`, `post-url`)
- **Database Tables**: 25 (`creative_asset`, `inbox_item_state` added 260923; `billing_webhook_event` added 260925)
- **Services**: 44 modules in `services/`
- **Background Workers**: 3 asyncio tasks (no Celery; there is no `workers/` package)
- **Frontend Pages**: 26 `page.tsx` files
- **Frontend Components**: 15 `ui/` primitive files + feature folders (`layout/`, `posts/`, `amplify/`, `clients/`, `setup/`, `create-content/`, `create-kits/`, `ads/`, `inbox/`, `insights/`, `settings/`, `agents/`, `landing/`) + app-level components; lib modules incl. 8 per-feature `api-*.ts` wrappers and `active-client.tsx`
- **Platform Integrations**: 8 (Clerk, Dodo Payments, AgentMail, Social publishing + Inbox reading, LLM, fal.ai, Slack, Exa)
- **LangGraph Nodes**: 9 (7 LLM agents + `human_review` + `compile_output`)
- **Agent Modules**: 19 (7 graph agents + 12 standalone: `autonomous_operator`, `competitive_intel`, `video_script`, `amplify`, and 260923's `post_writer`, `setup_profile`, `create_content`, `lifecycle_email`, `launch_pr`, `ads`, `advocacy`, `inbox_reply`)

> **Before deploying the Dodo Payments swap (260925):** run `db/migrations/260925_dodo_billing.sql` by hand on Neon, and set `DODO_API_KEY`, `DODO_WEBHOOK_KEY`, `DODO_ENVIRONMENT`, `DODO_PRODUCT_STARTER`, `DODO_PRODUCT_GROWTH`, `DODO_PRODUCT_AGENCY` and `FRONTEND_URL` as Fly secrets. Until then **billing is implemented but not live** — no checkout can complete. The five `STRIPE_*` vars are gone.

> **Before deploying manual publishing (260929):** run `db/migrations/260929_manual_channels.sql` by hand on Neon. It adds one nullable column (`platform_account.profile_url`), but SQLAlchemy names every mapped column in its `SELECT`, so skipping it takes down **every** `platform_account` read — publishing, inbox and analytics, not only the manual paths. No new env vars.

> **Before deploying `feat/cadence-parity`:** run `db/migrations/260923_creative_asset.sql`, then `260923_amplify_asset_source.sql`, then `260923_inbox.sql` by hand on Neon ([database-schema.md](database-schema.md#database-schema)). New optional env vars: `LINKEDIN_INBOX_SCOPE` (blank until the LinkedIn app is approved for comment reading), `LINKEDIN_API_VERSION` (default `202608`) — both in `.env.example` / `backend/.env.example`.

## Documents

| Document | Description | Last Updated |
|----------|-------------|-------------|
| [api-endpoints.md](api-endpoints.md) | All 138 REST API endpoints, approval gate, manual publishing, Amplify, generator contract, Setup, Post Studio, Create, Inbox, Insights, Workspace, OAuth | 260929 |
| [database-schema.md](database-schema.md) | 25 tables, columns, relationships, pending Neon migrations | 260929 |
| [services.md](services.md) | Business logic services, moderation, shared generator services, inbox, insights, scheduler reminders | 260929 |
| [workers.md](workers.md) | Asyncio background tasks | 260817 |
| [integrations.md](integrations.md) | Social publishing + Inbox reading, Dodo Payments, Clerk, AgentMail, LLM, fal.ai, Slack, Exa | 260925 |
| [websocket.md](websocket.md) | SSE real-time agent streaming (no WebSocket) | 260921 |
| [frontend-pages.md](frontend-pages.md) | 26 UI pages, top-nav IA + shortcuts, active client, Welcome, Setup, Create, Queue/Calendar, Inbox, Insights, Settings | 260929 |
| [frontend-components.md](frontend-components.md) | Design system, `ui/` primitives, shell, feature components, lib + `api-*` modules | 260929 |
| [auth-and-rbac.md](auth-and-rbac.md) | Clerk + legacy JWT, capability matrix, multi-tenancy, portal, OAuth state | 260929 |
| [billing.md](billing.md) | Dodo Payments billing (implemented, not yet live), 4 plan tiers, shared generation quota, post meter | 260929 |
| [changelog.md](changelog.md) | Chronological change log | 260929 |

## Feature Honesty

Everything below is either **real** or **visibly marked unavailable in the UI**. Nothing "looks real but isn't". Full evidence: [stub-audit-260817.md](../stub-audit-260817.md).

Fixed in Phase 1 (no longer stubs): analytics metrics (`analytics_fetcher.py` now calls real platform APIs, `NULL` not `0`), trending topics (`trends.py` via Exa), RAG (`knowledge_base.py` real cosine similarity + `retrieval_mode` label), webhooks (DB-backed + HMAC), competitive intel (source-URL gated).

Remaining gaps — all surfaced honestly to the user:

| Feature | Where | Reality | How the user is told |
|---------|-------|---------|----------------------|
| Paid plans / checkout | `services/billing.py`, `/pricing` | Dodo Payments is implemented in code but **no `DODO_*` secret is set in production** and no live catalogue exists — nobody has ever checked out, on Dodo or on the Stripe path before it | Not flagged in the UI: upgrade buttons are live and would fail at the Dodo call. Fix before inviting beta users to pay |
| Instagram publishing | `services/publishing.py` (T2.1) | Not implemented. <!-- verified: 260929 --> Since 260929 there is a *human* path: register the page as a manual channel and use "Post it yourself" | Publish button replaced by "Publishing unavailable" badge; API returns `success: false`. On a manual channel the button is **Post it yourself** instead, and the copy never says the product published it |
| TikTok publishing | no publisher exists | Not implemented; same manual path as Instagram | "draft only" badge on channel picker and repurpose targets |
| Metrics for hand-posted content | `services/platform_metrics.py`, `services/insights.py` | <!-- verified: 260929 --> **Permanently unavailable, not a gap to close.** A manual channel has no token and manual mode stores no platform post id, so a pasted link cannot be turned into a metric — the platforms require an authorized API call | "Posted manually — no link, metrics unavailable" on the card; `engagement.manual_unlinked` in the Insights summary. Excluded from averages, never a `0`, and still counted as published |
| Instagram metrics | `services/platform_metrics.py` (T2.2) | Returns `unavailable` | Content analytics shows the unavailable reason |
| Notifications | `services/notifications.py` | <!-- verified: 260929 --> One producer since 260929: the scheduler's `posts_due` reminder for hand-posted content. Nothing else writes notifications, and there is still no per-user preference column | Bell reads "nothing yet" honestly and links each digest to the filtered Queue; Settings → Notifications still shows "Not available yet" (no preferences to set) |
| "Connected" counts include manual channels | `routers/clients.py::clients_overview`, `/welcome`, `client-switcher.tsx` | <!-- verified: 260929 --> `clients/overview` returns `connected_accounts`, which since 260929 counts `status='manual'` rows too — the count is right, the name is not | **Not told honestly.** `/welcome` says "N accounts connected" and the switcher "N channel(s)" for a client that has only pages the operator posts by hand. Known issue; a rename (field + consumers) is owned by a follow-up, not the docs pass. The Insights figure is unaffected — `connected_platforms` is still OAuth-only |
| Channel chips omit manual channels | `components/posts/queue-sidebar.tsx`, `GET /post-studio/channels` | <!-- verified: 260929 --> That endpoint is connected-only by design (it feeds generation targets), so the Queue sidebar shows no chip for a page the operator posts by hand | Nothing states it. A manual-only client sees an empty channel row beside a working Post-it-yourself flow. Known issue; a fix belongs to the endpoint's owner |
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
│  Fly.io · 138 endpoints · 35 routers                 │
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
