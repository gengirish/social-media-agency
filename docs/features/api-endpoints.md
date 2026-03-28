# API Endpoints
<!-- verified: 260324 -->

All routes are prefixed with `/api/v1`. Authentication uses `Authorization: Bearer <JWT>` unless noted.

## Health

| Method | Path | Auth | Handler | Purpose |
|--------|------|------|---------|---------|
| GET | `/health` | No | `health` | Liveness check: `{status, service}` |
| GET | `/health/db` | No | `health_db` | DB probe via `SELECT 1` |

## Auth (Legacy)
**Status**: [LIVE]
**File**: `backend/src/agency/routers/auth.py`

| Method | Path | Auth | Handler | Purpose |
|--------|------|------|---------|---------|
| POST | `/auth/login` | No | `login` | Email/password login; returns JWT + role + org_id |
| POST | `/auth/signup` | No | `signup` | Creates org, admin user, free subscription; returns JWT |

## Clients
**Status**: [LIVE]
**File**: `backend/src/agency/routers/clients.py`

| Method | Path | Auth | Handler | Purpose |
|--------|------|------|---------|---------|
| POST | `/clients` | Yes | `create_client` | Create client for org |
| GET | `/clients` | Yes | `list_clients` | Paginated active clients |
| GET | `/clients/{client_id}` | Yes | `get_client` | Single client (org-scoped) |
| POST | `/clients/{client_id}/brand-profile` | Yes | `create_brand_profile` | Create BrandProfile for client |

## Campaigns
**Status**: [LIVE]
**File**: `backend/src/agency/routers/campaigns.py`

| Method | Path | Auth | Handler | Purpose |
|--------|------|------|---------|---------|
| POST | `/campaigns` | Yes | `create_campaign` | Create campaign + workflow, start LangGraph pipeline |
| GET | `/campaigns` | Yes | `list_campaigns` | Paginated campaigns; optional `client_id` filter |
| GET | `/campaigns/{campaign_id}` | Yes | `get_campaign` | Single campaign |
| GET | `/campaigns/{campaign_id}/content` | Yes | `get_campaign_content` | Content pieces for campaign |
| GET | `/campaigns/{campaign_id}/stream` | Token query | `stream_campaign` | SSE agent progress events (token via `?token=`) |
| PATCH | `/campaigns/{campaign_id}/review` | Yes | `submit_human_review` | Human review decision; resumes pipeline |

### SSE Stream Details

The stream endpoint uses `?token=` query param because `EventSource` cannot send Authorization headers. Token verification: Clerk JWKS first, then legacy JWT fallback. Returns `AgentStreamEvent` JSON objects with types: `step_start`, `step_complete`, `waiting_human`, `complete`, `error`, `heartbeat`.

## Content
**Status**: [LIVE]
**File**: `backend/src/agency/routers/content.py`

| Method | Path | Auth | Handler | Purpose |
|--------|------|------|---------|---------|
| GET | `/content` | Yes | `list_content` | Paginated; filters: campaign_id, client_id, status, platform |
| GET | `/content/{content_id}` | Yes | `get_content` | Single content piece |
| PATCH | `/content/{content_id}` | Yes | `update_content` | Partial update (title, body, hashtags, status) |
| POST | `/content/{content_id}/approve` | Yes | `approve_content` | Set status to `approved` |

## Stats
**Status**: [LIVE]
**File**: `backend/src/agency/routers/stats.py`

| Method | Path | Auth | Handler | Purpose |
|--------|------|------|---------|---------|
| GET | `/stats` | Yes | `get_dashboard_stats` | Dashboard counts (clients, campaigns, content, agent runs, running, drafts) |

## Billing
**Status**: [LIVE]
**File**: `backend/src/agency/routers/billing.py`

| Method | Path | Auth | Handler | Purpose |
|--------|------|------|---------|---------|
| GET | `/billing/plans` | Yes | `list_plans` | Plan catalog |
| GET | `/billing/subscription` | Yes | `get_subscription` | Org subscription + limits |
| POST | `/billing/checkout` | Yes | `create_checkout` | Stripe Checkout session |
| POST | `/billing/webhook` | Stripe sig | `stripe_webhook` | Stripe webhook handler |

## Publishing
**Status**: [LIVE]
**File**: `backend/src/agency/routers/publishing.py`

| Method | Path | Auth | Handler | Purpose |
|--------|------|------|---------|---------|
| POST | `/publishing/{content_id}/publish` | Yes | `publish_now` | Publish immediately via PlatformPublisher |
| POST | `/publishing/{content_id}/schedule` | Yes | `schedule_content` | Schedule content; body: `scheduled_at` |
| GET | `/publishing/calendar` | Yes | `get_calendar` | Scheduled/published items in date range |

## Team
**Status**: [LIVE]
**File**: `backend/src/agency/routers/team.py`

| Method | Path | Auth | Handler | Purpose |
|--------|------|------|---------|---------|
| GET | `/team` | Yes | `get_team` | List org members |
| POST | `/team/invite` | Yes | `invite_member` | Invite user (temp password; best-effort AgentMail) |
| PATCH | `/team/{user_id}/role` | Yes | `patch_member_role` | Change member role |

## Magic Brief
**Status**: [LIVE]
**File**: `backend/src/agency/routers/magic_brief.py`

| Method | Path | Auth | Handler | Purpose |
|--------|------|------|---------|---------|
| POST | `/magic-brief` | Yes | `create_magic_brief` | Brand extraction from URL via LLM |

## Integrations
**Status**: [LIVE]
**File**: `backend/src/agency/routers/integrations.py`

| Method | Path | Auth | Handler | Purpose |
|--------|------|------|---------|---------|
| POST | `/integrations/api-keys` | Yes | `create_key` | Create API key |
| GET | `/integrations/api-keys` | Yes | `list_keys` | List org API keys (metadata only) |
| DELETE | `/integrations/api-keys/{key_id}` | Yes | `revoke_key` | Deactivate API key |
| GET | `/integrations/white-label` | Yes | `get_branding` | White-label settings |
| PUT | `/integrations/white-label` | Yes | `update_branding` | Upsert white-label |
| GET | `/integrations/templates` | Yes | `list_templates` | Campaign templates; optional `category` |
| POST | `/integrations/templates` | Yes | `create_template` | Create org template |

**Total: 36 endpoints across 10 routers**
