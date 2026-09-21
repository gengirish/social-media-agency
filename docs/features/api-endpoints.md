# API Endpoints
<!-- verified: 260921 -->

All routes are prefixed with `/api/v1`. Authentication uses `Authorization: Bearer <JWT>` unless noted. `ApiKeyAuthMiddleware` accepts `X-API-Key` for `/public/*` and other key-gated routes as implemented.

## Health

| Method | Path | Auth | Handler | Purpose |
|--------|------|------|---------|---------|
| GET | `/health` | No | `health` | Liveness check: `{status, service}` |
| GET | `/health/db` | No | `health_db` | DB probe via `SELECT 1` |
| GET | `/health/llm` | Yes | `health_llm` | Resolved provider/model/fallbacks per tier; never returns keys |

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
| GET | `/content` | Yes | `list_content` | Paginated (`page`, `per_page` ≤100); filters: `campaign_id`, `client_id`, `content_status`, `platform`. The status filter is **`content_status`** — a `status` param is silently ignored |
| GET | `/content/suggestions` | Yes | `content_suggestions` | Top-performing content for recycling |
| POST | `/content/video-script` | Yes | `create_video_script` | Generate video/podcast scripts |
| GET | `/content/{content_id}` | Yes | `get_content` | Single content piece |
| GET | `/content/{content_id}/analytics` | Yes | `get_analytics` | Analytics snapshots for content |
| PATCH | `/content/{content_id}` | Yes | `update_content` | Partial update (title, body, hashtags, status). `status` only `draft`/`rejected` — see [Approval gate](#approval-gate) |
| POST | `/content/{content_id}/repurpose` | Yes | `repurpose_content` | Generate platform-adapted variants (lite tier, one per platform). Kept for API compatibility; the UI uses [Amplify](#amplify) instead |
| POST | `/content/{content_id}/variants` | Yes | `generate_variants` | A/B variant generation |
| POST | `/content/{content_id}/approve` | Yes | `approve_content` | Moderate, then approve; `?override=true` approves over flagged issues — see [Approval gate](#approval-gate) |
| POST | `/content/{content_id}/generate-image` | Yes | `generate_image` | AI image generation via fal.ai |

### Approval gate

Product rule 3: moderation runs before approval, and only approved content can be scheduled or published. Publishing is real (X, LinkedIn, Facebook), so these gates guard live client accounts. Logic lives in `services/content_approval.py` + `services/moderation.py`.

Lifecycle (DB values; `draft` is labelled *Pending* in the UI): `draft`/`rejected` → **approve** → `approved` → **schedule** → `scheduled` → `published`, or `approved`/`scheduled` → **publish now** → `published`.

**`POST /content/{id}/approve[?override=true]`** — only `draft` or `rejected` pieces.

| Outcome | Status | Body |
|---|---|---|
| No issues | 200 | `{"id", "status": "approved", "moderation": {"status": "passed"\|"unavailable", "issues": []}}` |
| Issues, no override | 409 | `detail = {"code": "moderation_flagged", "issues": [{"severity": "low"\|"medium"\|"high", "message"}]}` — status unchanged |
| Issues, `override=true` | 200 | `moderation.status = "overridden"`; `metadata.moderation` records `issues`, `override_by` (caller user id), `at` |
| Not `draft`/`rejected` | 409 | `detail = {"code": "invalid_status", "status": <current>}` |

`moderation.status = "unavailable"` means the LLM check failed open (error, timeout, unparseable reply, no provider) — the piece is approved, `moderation_unavailable` is logged, and `metadata.moderation.status` records it. The deterministic checks (platform character limit incl. appended hashtags; brand `vocabulary_exclude`) run regardless and still flag when the LLM is down.

**`PATCH /content/{id}`** — `status` may be set to `draft` or `rejected` only. `approved`/`scheduled`/`published` → 400 `{"code": "status_via_dedicated_endpoint"}`; any other value → 400 `{"code": "unsupported_status"}`. Changing `body` or `hashtags` of an `approved`/`scheduled` piece **resets it to `draft`** (clears `scheduled_at` and `metadata.moderation`) — edited content must be re-approved.

**`POST /publishing/{id}/schedule`, `POST /publishing/{id}/publish`** — only `approved` or `scheduled` pieces; otherwise 409 `{"code": "not_approved", "status": <current>}` (including `published`, so a repeated publish cannot double-post). The scheduler loop only ever publishes `scheduled` rows.

**Portal** `PATCH /portal/{org_slug}/content/{id}` with `decision: "approve"` runs the same moderation with **no override**; a flag returns the same 409 `moderation_flagged` shape.

## Amplify
**Status**: [LIVE] (output quality not yet reviewed against a live LLM)
**File**: `backend/src/agency/routers/amplify.py` · agent `agents/amplify.py` · helpers `services/repurpose.py`
<!-- verified: 260921 -->

One source (an existing content piece or pasted text) → up to 8 drafts, each on a different angle from a closed taxonomy (`hook`, `how-to`, `contrarian`, `story`, `data-point`, `question`, `behind-the-scenes`, `listicle`). Two steps on purpose: **preview** generates and writes nothing to `content_piece`; **commit** writes only the atoms the human kept, always as `status="draft"` (Pending). Nothing here approves, schedules or publishes — committed drafts go through the normal [approval gate](#approval-gate).

| Method | Path | Auth | Handler | Purpose |
|--------|------|------|---------|---------|
| POST | `/amplify/preview` | Yes | `preview` | Generate a pack. Charges 1 generation on success |
| POST | `/amplify/{pack_id}/commit` | Yes | `commit` | Write kept atoms as Pending drafts |
| GET | `/amplify/packs` | Yes | `list_packs` | Pack history for the org, newest first |

Tenancy: `client_id`, `source_content_id` and `pack_id` are each resolved against the caller's `org_id` (covered in `test_tenancy_routers.py`).

**`POST /amplify/preview`**

Request:

```json
{
  "client_id": "uuid",
  "source_content_id": "uuid | null",
  "source_text": "string | null (≤20000 chars)",
  "platforms": ["twitter", "linkedin", "instagram", "facebook", "tiktok"],
  "max_atoms": 8
}
```

Exactly one of `source_content_id` / `source_text` (non-blank). `platforms` ≥1, each a key of `PLATFORM_CHAR_LIMITS`. `max_atoms` 1–8, default 8. A `source_content_id` must belong to the same org **and** the same client.

Response 200:

```json
{
  "pack_id": "uuid",
  "atoms": [{
    "platform": "linkedin", "angle": "how-to", "title": "...", "body": "...",
    "hashtags": ["tag"], "char_count": 812, "char_limit": 3000,
    "duplicate_warning": false
  }],
  "requested": 8,
  "dropped": 1
}
```

- Angles are assigned before the LLM call (`plan_atoms`): platforms rotate, and angles already used by earlier packs from the same source go last. The model's output is re-validated — off-plan, over-limit, empty or repeated-angle atoms are dropped and counted in `dropped`.
- `char_count` is body + `"

"` + all hashtags as `#tag`; atoms over `char_limit` are dropped, never returned.
- `duplicate_warning` — token-set Jaccard ≥ 0.6 against the client's 50 most recent posts and the earlier atoms in this pack. Warns, never blocks.
- Brand context: client fields plus the client's `BrandProfile` (voice, tone, vocabulary include/exclude, up to 3 `example_posts`, style rules, emoji policy, audience). When the source belongs to a campaign, the campaign's name, objective and channels are added.
- On success a `repurpose_pack` row is written, `subscription.generations_used` is incremented, and the server-authored `amplify_pack_generated` event is tracked.

| Error | Status | Body |
|---|---|---|
| Client not in org | 404 | `"Client not found"` |
| Source not in org/client | 404 | `"Source content not found"` |
| Source piece has no title/body | 422 | `"Source content is empty"` |
| Validation (both/neither source, unknown platform, `max_atoms` out of range) | 422 | FastAPI validation error |
| No subscription row, or `generations_used >= limit` | 402 | `detail = {"code": "generation_quota_exceeded", "message"}` |
| LLM raised | 502 | `"Generation failed; no quota was used. Try again."` |
| No atom survived validation | 502 | `"The model returned no usable drafts; no quota was used. Try again."` |

Quota is checked *before* generation and incremented (atomically, `generations_used + 1`) *after* — a 502 charges nothing. The check and the increment are not one statement, so concurrent previews at the limit can each pass the check and overshoot it.

**`POST /amplify/{pack_id}/commit`**

Request: `{"atoms": [{"platform", "angle", "title": "", "body", "hashtags": []}]}` — 1 to 8 atoms.

Response 200: `{"created": ["content_id", ...], "count": n}`.

Each kept atom becomes a `content_piece` with `status="draft"` (hard-coded), `content_type="social_post"`, `ai_generated=true`, `campaign_id` inherited from the source piece if any, and `metadata = {amplify_pack_id, source_id, angle}`. Sets `repurpose_pack.committed_count`; tracks `amplify_pack_committed`. Commit does not re-run the LLM and does not charge quota.

| Error | Status | Body |
|---|---|---|
| Pack not in org | 404 | `"Pack not found"` |
| Pack already committed (`committed_count > 0`) | 409 | `"This pack was already added to the queue"` |
| Atom fails re-validation (platform not in the pack's platforms, unknown/duplicate angle, empty body, over char limit) | 422 | `detail = {"code": "invalid_atoms", "errors": [...]}` |
| 0 or >8 atoms | 422 | FastAPI validation error |

**`GET /amplify/packs?client_id=&limit=20`** — `limit` 1–100. Returns `{"items": [{id, client_id, client_name, source_content_id, source_title, source_excerpt (first 140 chars of pasted text), platforms, atom_count, committed_count, created_at}]}`.

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
| GET | `/billing/subscription` | Yes | `get_subscription` | Org subscription + limits, incl. `generations_used` / `generations_limit` (Amplify quota — see [billing.md](billing.md#amplify-generation-quota)) |
| POST | `/billing/checkout` | Yes | `create_checkout` | Stripe Checkout session |
| POST | `/billing/webhook` | Stripe sig | `stripe_webhook` | Stripe webhook handler |

## Publishing
**Status**: [LIVE]
**File**: `backend/src/agency/routers/publishing.py`

| Method | Path | Auth | Handler | Purpose |
|--------|------|------|---------|---------|
| POST | `/publishing/{content_id}/publish` | Yes | `publish_now` | Publish immediately via PlatformPublisher; `approved`/`scheduled` only, else 409 `not_approved` |
| POST | `/publishing/{content_id}/schedule` | Yes | `schedule_content` | Schedule content; body: `scheduled_at`; `approved`/`scheduled` only, else 409 `not_approved` |
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
> `{org_slug}` resolves against `Organization.slug` **only** (unique, nullable). It previously fell back to `domain` then `name`, neither of which is unique — two orgs sharing a name 500'd every portal route. An org with no slug has no portal and returns 404.

| GET | `/portal/{org_slug}/campaigns` | No | `portal_campaigns` | White-label campaign list |
| GET | `/portal/{org_slug}/content` | No | `portal_content` | White-label content list |
| PATCH | `/portal/{org_slug}/content/{content_id}` | No | `portal_review_content` | Client approve (moderated, no override — 409 `moderation_flagged`) / reject |

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

## Product Analytics
**Status**: [LIVE]
**File**: `backend/src/agency/routers/product_analytics.py`

| Method | Path | Auth | Handler | Purpose |
|--------|------|------|---------|---------|
| POST | `/events` | Yes | `ingest_events` | Batch browser events (≤50). Only `session_started`, `session_ended`, `page_view`, `feature_used` are accepted; others counted as rejected |
| GET | `/beta-metrics` | Yes | `get_beta_metrics` | Beta plan §7 metrics for the caller's org (`window_days`, 1–180, default 28) |

**Total: 86 endpoints across 25 routers** (counted from `@router.*` decorators, 260921) — every router file in `routers/` is mounted in `main.py` with prefix `/api/v1`.

Note: `product_analytics.py` declares no router prefix, so its two routes land at `/api/v1/events` and `/api/v1/beta-metrics`. `slack.py` and `webhooks_config.py` both nest under the `/integrations` path without being part of `integrations.py`.
