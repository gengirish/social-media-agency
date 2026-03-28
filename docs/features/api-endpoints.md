# API Endpoints
<!-- verified: 260328 -->

All routes are prefixed with `/api/v1`. Authentication uses `Authorization: Bearer <JWT>` unless noted. `ApiKeyAuthMiddleware` accepts `X-API-Key` for `/public/*` and other key-gated routes as implemented.

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
| GET | `/campaigns/trends` | Yes | `get_trends` | Trending topics per platform |
| POST | `/campaigns/autonomous` | Yes | `create_autonomous_campaign` | Create autonomous weekly-cycle campaign |
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
| GET | `/content/suggestions` | Yes | `content_suggestions` | Top-performing content for recycling |
| POST | `/content/video-script` | Yes | `create_video_script` | Generate video/podcast scripts |
| GET | `/content/{content_id}` | Yes | `get_content` | Single content piece |
| GET | `/content/{content_id}/analytics` | Yes | `get_analytics` | Analytics snapshots for content |
| PATCH | `/content/{content_id}` | Yes | `update_content` | Partial update (title, body, hashtags, status) |
| POST | `/content/{content_id}/repurpose` | Yes | `repurpose_content` | Generate platform-adapted variants |
| POST | `/content/{content_id}/variants` | Yes | `generate_variants` | A/B variant generation |
| POST | `/content/{content_id}/approve` | Yes | `approve_content` | Set status to `approved` |
| POST | `/content/{content_id}/generate-image` | Yes | `generate_image` | AI image generation via fal.ai |

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
| GET | `/integrations/settings` | Yes | `get_settings_endpoint` | Org settings |
| PATCH | `/integrations/settings` | Yes | `update_settings_endpoint` | Update org settings |
| GET | `/integrations/platform-accounts` | Yes | `list_platform_accounts` | Connected platform accounts |
| GET | `/integrations/templates` | Yes | `list_templates` | Campaign templates; optional `category` |
| POST | `/integrations/templates` | Yes | `create_template` | Create org template |
| GET | `/integrations/templates/marketplace` | Yes | `list_marketplace_templates` | Public template marketplace |
| GET | `/integrations/templates/{template_id}` | Yes | `get_template` | Template details |
| POST | `/integrations/templates/{template_id}/launch` | Yes | `launch_template` | Pre-fill campaign from template |
| POST | `/integrations/templates/{template_id}/fork` | Yes | `fork_template` | Clone public template |
| POST | `/integrations/templates/{template_id}/publish` | Yes | `publish_template` | Make template public |

## OAuth
**Status**: [LIVE]
**File**: `backend/src/agency/routers/oauth.py`

| Method | Path | Auth | Handler | Purpose |
|--------|------|------|---------|---------|
| GET | `/oauth/{platform}/authorize` | Yes | `get_oauth_url` | OAuth authorization URL |
| POST | `/oauth/{platform}/callback` | Yes | `oauth_callback` | Exchange code for tokens |
| DELETE | `/oauth/{platform}/{account_id}` | Yes | `disconnect_platform` | Disconnect platform |

## Reports
**Status**: [LIVE]
**File**: `backend/src/agency/routers/reports.py`

| Method | Path | Auth | Handler | Purpose |
|--------|------|------|---------|---------|
| POST | `/reports/clients/{client_id}` | Yes | `create_report` | Generate client report |
| GET | `/reports/clients/{client_id}` | Yes | `list_reports` | List report periods |

## Comments
**Status**: [LIVE]
**File**: `backend/src/agency/routers/comments.py`

| Method | Path | Auth | Handler | Purpose |
|--------|------|------|---------|---------|
| POST | `/comments/content/{content_id}` | Yes | `add_comment` | Add comment |
| GET | `/comments/content/{content_id}` | Yes | `list_comments` | List comments |
| DELETE | `/comments/{comment_id}` | Yes | `delete_comment` | Delete own comment |

## Notifications
**Status**: [LIVE]
**File**: `backend/src/agency/routers/notifications.py`

| Method | Path | Auth | Handler | Purpose |
|--------|------|------|---------|---------|
| GET | `/notifications` | Yes | `list_notifications` | User notifications |
| PATCH | `/notifications/{id}/read` | Yes | `mark_read` | Mark notification read |
| PATCH | `/notifications/read-all` | Yes | `mark_all_read` | Mark all read |

## Brand Analytics
**Status**: [LIVE]
**File**: `backend/src/agency/routers/brand_analytics.py`

| Method | Path | Auth | Handler | Purpose |
|--------|------|------|---------|---------|
| GET | `/brand-analytics/clients/{client_id}/intelligence` | Yes | `get_client_intelligence` | Client intelligence dashboard |
| GET | `/brand-analytics/cross-learning` | Yes | `get_cross_learning` | Cross-campaign insights |

## Competitive Intelligence
**Status**: [LIVE]
**File**: `backend/src/agency/routers/competitive.py`

| Method | Path | Auth | Handler | Purpose |
|--------|------|------|---------|---------|
| POST | `/competitive/clients/{client_id}/scan` | Yes | `trigger_competitive_scan` | Run competitive scan |

## Portal
**Status**: [LIVE]
**File**: `backend/src/agency/routers/portal.py`

| Method | Path | Auth | Handler | Purpose |
|--------|------|------|---------|---------|
| GET | `/portal/{org_slug}/campaigns` | No | `portal_campaigns` | White-label campaign list |
| GET | `/portal/{org_slug}/content` | No | `portal_content` | White-label content list |
| PATCH | `/portal/{org_slug}/content/{content_id}` | No | `portal_review_content` | Client approve/reject |

## Slack
**Status**: [LIVE]
**File**: `backend/src/agency/routers/slack.py`

| Method | Path | Auth | Handler | Purpose |
|--------|------|------|---------|---------|
| POST | `/integrations/slack/events` | Slack sig | `handle_slack_event` | Slack event handler |
| POST | `/integrations/slack/commands` | Slack sig | `handle_slash_command` | Slash command handler |

## Webhooks
**Status**: [LIVE]
**File**: `backend/src/agency/routers/webhooks_config.py`

| Method | Path | Auth | Handler | Purpose |
|--------|------|------|---------|---------|
| POST | `/integrations/webhooks` | Yes | `register_webhook` | Register webhook URL |
| GET | `/integrations/webhooks` | Yes | `list_webhooks` | List webhooks |
| DELETE | `/integrations/webhooks/{webhook_id}` | Yes | `delete_webhook` | Remove webhook |

## Public API
**Status**: [LIVE]
**File**: `backend/src/agency/routers/public_api.py`

Authentication: `X-API-Key` header (API key), not JWT.

| Method | Path | Auth | Handler | Purpose |
|--------|------|------|---------|---------|
| GET | `/public/me` | API Key | `public_me` | API key org info |
| GET | `/public/campaigns` | API Key | `public_list_campaigns` | List campaigns via API key |

## Acquisition
**Status**: [LIVE]
**File**: `backend/src/agency/routers/acquisition.py`

| Method | Path | Auth | Handler | Purpose |
|--------|------|------|---------|---------|
| POST | `/acquisition/outreach` | Yes | `generate_outreach_sequence` | Generate prospect outreach |

## Audit
**Status**: [LIVE]
**File**: `backend/src/agency/routers/audit.py`

| Method | Path | Auth | Handler | Purpose |
|--------|------|------|---------|---------|
| GET | `/audit` | Yes | `list_audit_logs` | Audit trail (enterprise) |

**Total: 83 endpoints across 20 routers**
