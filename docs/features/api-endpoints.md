# API Endpoints
<!-- verified: 260923 -->

All routes are prefixed with `/api/v1`. Authentication uses `Authorization: Bearer <JWT>` unless noted. `ApiKeyAuthMiddleware` accepts `X-API-Key` for `/public/*` and other key-gated routes as implemented.

## Health

| Method | Path | Auth | Handler | Purpose |
|--------|------|------|---------|---------|
| GET | `/health` | No | `health` | Liveness check: `{status, service}` |
| GET | `/health/db` | No | `health_db` | DB probe via `SELECT 1` |
| GET | `/health/llm` | Yes | `health_llm` | Resolved provider/model/fallbacks per tier; never returns keys |
| GET | `/health/email` | Yes | `health_email` | Whether transactional email can actually send. Read `can_send` (live sender-inbox resolution), not `configured` (key merely present) |

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
| GET | `/clients[?archived=true]` | Yes | `list_clients` | Paginated active clients, or archived ones with `archived=true` |
| GET | `/clients/overview` | Yes | `clients_overview` | [LIVE] <!-- verified: 260923 --> Per **active** client: `{id, brand_name, website_url, has_brand_profile, connected_accounts, total_posts, pending, approved, scheduled, published, failed, campaign_focus}` — real counts only. Backs the top-nav client switcher and `/welcome`. Declared before `/{client_id}` so `overview` is not parsed as an id |
| PUT | `/clients/{client_id}/campaign-focus` | Yes | `set_campaign_focus` | [LIVE] Body `{description}` (1–300 chars). Stores Cadence's human-typed "Campaign" at `client.settings.campaign_focus = {description, set_at}`; returns `{campaign_focus}`. No AI involved |
| DELETE | `/clients/{client_id}/campaign-focus` | Yes | `clear_campaign_focus` | [LIVE] Removes it; returns `{campaign_focus: null}` |
| GET | `/clients/{client_id}` | Yes | `get_client` | Single client (org-scoped); returns archived clients too, with `is_active: false` |
| PATCH | `/clients/{client_id}` | Yes | `update_client` | Partial update of `brand_name`, `industry`, `description`, `website_url`, `contact_email`; only fields sent are written; explicit `null` for `brand_name`/`industry` → 422 |
| POST | `/clients/{client_id}/archive[?unschedule=true]` | Yes | `archive_client` | Soft delete (`is_active = false`), see below |
| POST | `/clients/{client_id}/restore` | Yes | `restore_client` | Undo archive |
| POST | `/clients/{client_id}/brand-profile` | Yes | `create_brand_profile` | Create BrandProfile for client (fails if one exists; use PUT) |
| GET | `/clients/{client_id}/brand-profile` | Yes | `get_brand_profile` | Saved BrandProfile (`BrandProfileResponse`); 404 when the client has none |
| PUT | `/clients/{client_id}/brand-profile` | Yes | `upsert_brand_profile` | Create if missing, otherwise update only the fields sent |

<!-- verified: 260922 -->
**Archive** keeps campaigns, posts and history, and hides the client from `GET /clients`. Scheduled posts would otherwise go live after the archive, so while any exist it returns 409 `{"code": "has_scheduled_posts", "count": n}`; `?unschedule=true` moves them back to `approved` (clearing `scheduled_at`) in the same transaction. After an archive, schedule and publish-now for that client's posts return 409 `{"code": "client_archived"}` (see [Approval gate](#approval-gate)).

Tenancy: every handler resolves `client_id` against the caller's `org_id` first (404 otherwise). Tests: `tests/test_client_edit.py`.

**Campaign focus** is read by every generator through `services/brand_context.py::brand_prompt_block` ("Active campaign right now: …"), except the PRFAQ stress-test, which deliberately ignores it. Shown and edited by `CampaignIndicator` and Setup › Profile. Tests: `tests/test_foundation.py`.

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

Five more `/content` routes (`POST /content`, `POST /content/generate`, `POST /content/{id}/regenerate`, `POST /content/{id}/creative-brief`, `DELETE /content/{id}`) live in `routers/post_studio.py` — see [Post Studio](#post-studio-queue--calendar-actions).

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

<!-- verified: 260923 --> Since 260923 a 409 `moderation_flagged` also records a server-authored `moderation_flagged` product event (`{content_id, client_id, platform, issue_count}`) — the piece itself is untouched — and an edit to the body/hashtags of a still-Pending piece sets `metadata.edited_before_approval = true`. Both feed Insights' quality signal and the activity log.

`moderation.status = "unavailable"` means the LLM check failed open (error, timeout, unparseable reply, no provider) — the piece is approved, `moderation_unavailable` is logged, and `metadata.moderation.status` records it. The deterministic checks (platform character limit incl. appended hashtags; brand `vocabulary_exclude`) run regardless and still flag when the LLM is down.

**`PATCH /content/{id}`** — `status` may be set to `draft` or `rejected` only. `approved`/`scheduled`/`published` → 400 `{"code": "status_via_dedicated_endpoint"}`; any other value → 400 `{"code": "unsupported_status"}`. A `published` piece cannot change status at all → 409 `{"code": "published_locked"}` (reopening it would allow a second live post). Changing `body` or `hashtags` of an `approved`/`scheduled` piece **resets it to `draft`** (clears `scheduled_at` and `metadata.moderation`) — edited content must be re-approved.

**`POST /publishing/{id}/schedule`, `POST /publishing/{id}/publish`** — only `approved` or `scheduled` pieces; otherwise 409 `{"code": "not_approved", "status": <current>}` (including `published`, so a repeated publish cannot double-post). Schedule additionally refuses platforms with no working publisher (Instagram, TikTok) → 409 `{"code": "platform_unavailable", "platform", "reason"}`, since a scheduled post there would only fail when due. The scheduler loop only ever publishes `scheduled` rows. Both endpoints, and the scheduler when a post comes due, also refuse posts whose client is archived → 409 `{"code": "client_archived"}` (the scheduler marks the post `failed` with `publish_error: "Client is archived"`).

**Portal** `PATCH /portal/{org_slug}/content/{id}` with `decision: "approve"` runs the same moderation with **no override**; a flag returns the same 409 `moderation_flagged` shape.

## Amplify
**Status**: [LIVE] (output quality not yet reviewed against a live LLM)
**File**: `backend/src/agency/routers/amplify.py` · agent `agents/amplify.py` · helpers `services/repurpose.py`
<!-- verified: 260921 -->

One source (an existing content piece, a saved Create-screen asset, or pasted text) → up to 8 drafts, each on a different angle from a closed taxonomy (`hook`, `how-to`, `contrarian`, `story`, `data-point`, `question`, `behind-the-scenes`, `listicle`). Two steps on purpose: **preview** generates and writes nothing to `content_piece`; **commit** writes only the atoms the human kept, always as `status="draft"` (Pending). Nothing here approves, schedules or publishes — committed drafts go through the normal [approval gate](#approval-gate).

| Method | Path | Auth | Handler | Purpose |
|--------|------|------|---------|---------|
| POST | `/amplify/preview` | Yes | `preview` | Generate a pack. Charges 1 generation on success |
| POST | `/amplify/{pack_id}/commit` | Yes | `commit` | Write kept atoms as Pending drafts |
| GET | `/amplify/packs` | Yes | `list_packs` | Pack history for the org, newest first |

Tenancy: `client_id`, `source_content_id`, `source_asset_id` and `pack_id` are each resolved against the caller's `org_id` (covered in `test_tenancy_routers.py` and `test_create_content.py`).

**`POST /amplify/preview`**

Request:

```json
{
  "client_id": "uuid",
  "source_content_id": "uuid | null",
  "source_asset_id": "uuid | null",
  "source_text": "string | null (≤20000 chars)",
  "platforms": ["twitter", "linkedin", "instagram", "facebook", "tiktok"],
  "max_atoms": 8
}
```

Exactly one of `source_content_id` / `source_asset_id` / `source_text` (non-blank). <!-- verified: 260923 --> A `source_asset_id` must be a `creative_asset` of the same org **and** client (404 `Source asset not found`), of a kind in `REPURPOSABLE_ASSET_KINDS` — `blog_post`, `comparison_page`, `niche_scan`, `video_script`, `launch_kit` (else 422). Its text is flattened by `services/create_content.py::asset_source_text` (422 `Source asset is empty`). The id is stored on `repurpose_pack.source_asset_id` and on each committed atom's `metadata.source_asset_id`, and angles already used from the same asset go last, as for a content source. `platforms` ≥1, each a key of `PLATFORM_CHAR_LIMITS`. `max_atoms` 1–8, default 8. A `source_content_id` must belong to the same org **and** the same client.

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

Quota is checked *before* generation (`services/generation_quota.py`, shared by every generator since 260923) and incremented (atomically, `generations_used + 1`) *after* — a 502 charges nothing. The check and the increment are not one statement, so concurrent previews at the limit can each pass the check and overshoot it.

**`POST /amplify/{pack_id}/commit`**

Request: `{"atoms": [{"platform", "angle", "title": "", "body", "hashtags": []}]}` — 1 to 8 atoms.

Response 200: `{"created": ["content_id", ...], "count": n}`.

Each kept atom becomes a `content_piece` with `status="draft"` (hard-coded), `content_type="social_post"`, `ai_generated=true`, `campaign_id` inherited from the source piece if any, and `metadata = {amplify_pack_id, source_id, source_asset_id, angle}`. Sets `repurpose_pack.committed_count`; tracks `amplify_pack_committed`. Commit does not re-run the LLM and does not charge quota.

| Error | Status | Body |
|---|---|---|
| Pack not in org | 404 | `"Pack not found"` |
| Pack already committed (`committed_count > 0`) | 409 | `"This pack was already added to the queue"` |
| Atom fails re-validation (platform not in the pack's platforms, unknown/duplicate angle, empty body, over char limit) | 422 | `detail = {"code": "invalid_atoms", "errors": [...]}` |
| 0 or >8 atoms | 422 | FastAPI validation error |

**`GET /amplify/packs?client_id=&limit=20`** — `limit` 1–100. Returns `{"items": [{id, client_id, client_name, source_content_id, source_asset_id, source_title (content title, else asset title), source_excerpt (first 140 chars of pasted text), platforms, atom_count, committed_count, created_at}]}`.

## Shared generator contract (260923)
<!-- verified: 260923 -->

Every Cadence-parity generator (Setup brand voice / strategy lens, Post Studio, Create › Content / Email / Launch / Ads, Insights advocacy, Inbox reply suggestions) follows Amplify's shape:

1. Resolve `client_id` (or the asset / content id) against the caller's `org_id` → 404 across orgs (`services/brand_context.py::get_org_client`).
2. Content / Email / Launch additionally require a brand profile → 409 `{"code": "brand_profile_required"}`; Setup's Brand Voice / Strategy Lens require an approved profile → 409 `{"code": "profile_required"}`. **Ads, Post Studio, advocacy and inbox suggestions have no profile gate.**
3. `require_generation_quota` → 402 `{"code": "generation_quota_exceeded", "message"}` before the model is called.
4. Model call, then the reply's shape is validated in code. Model error or malformed reply → **502** "…no quota was used. Try again."; nothing is saved or charged.
5. Long-form output is saved as a `creative_asset` (see [Assets](#creative-assets)); social posts go to `content_piece` as `draft`, never approved/scheduled.
6. `charge_generation` (+1 `generations_used`), then commit. 1 generation per successful call.

Brand context is `load_brand_context` + `brand_prompt_block`: client basics, brand profile, the Setup › Profile tone register, `posting_prefs` (voice register, cadence) and the client's campaign focus.

## Creative Assets
**Status**: [LIVE]
**File**: `backend/src/agency/routers/assets.py` · store `services/creative_assets.py` · table [`creative_asset`](database-schema.md#creativeasset)
<!-- verified: 260923 -->

Generic read / rename / delete for the Create screens' saved output. Generation lives in each feature's own router.

| Method | Path | Auth | Handler | Purpose |
|--------|------|------|---------|---------|
| GET | `/assets?client_id=&kind=&q=&limit=&offset=` | Yes | `list_assets` | `{items, total}`, newest first. `client_id` required and org-resolved; `kind` repeatable (unknown kind → 422); `q` case-insensitive title search (≤200); `limit` 1–200 (default 50) |
| GET | `/assets/{asset_id}` | Yes | `get_asset` | One asset (404 across orgs) |
| PATCH | `/assets/{asset_id}` | Yes | `update_asset` | `{title?, payload?}` — rename or replace the payload |
| DELETE | `/assets/{asset_id}` | Yes | `delete_asset` | 204. Hard delete; the UI offers undo by delaying the call |

Asset shape: `{id, client_id, kind, title, payload, source_asset_id, created_at, updated_at}`. `kind` ∈ `ASSET_KINDS`: `blog_post`, `comparison_page`, `niche_scan`, `video_script` (Content), `email_campaign` (Email), `launch_kit`, `community_kit`, `outreach_pitch` (Launch), `ad_set` (Ads), `advocacy` (Insights), `strategy_lens` (Setup). Tests: `tests/test_foundation.py`.

## Setup (Profile + Accounts)
**Status**: [LIVE]
**File**: `backend/src/agency/routers/setup.py` · services `services/setup_profile.py` · agent `agents/setup_profile.py` (worker tier)
<!-- verified: 260923 -->

Cadence's IntakeScreen and ConnectScreen for one client. Every route is `/setup/{client_id}/…` (the frontend pages are `/setup/profile` and `/setup/accounts`, scoped by the active client). The website scan itself is the existing `POST /magic-brief`.

| Method | Path | Auth | Handler | Purpose |
|--------|------|------|---------|---------|
| GET | `/setup/{client_id}/profile` | Yes | `read_profile` | Intake answers, brand voice guide, campaign focus |
| PUT | `/setup/{client_id}/profile` | Yes | `approve_profile` | Approve the intake: `{url?, audience, differentiator, tone}` (answers ≤600 chars, non-blank; `tone` ∈ `Blunt & technical`, `Friendly & casual`, `Bold & punchy`, `Calm & authoritative`). Creates or merges the brand profile — never wipes |
| POST | `/setup/{client_id}/profile/evaluate-answer` | Yes | `coach_answer` | `{question_id: audience\|differentiator, answer}` → `{available, is_thin, coaching_note}`. Advisory, **not charged**, fails open (`available: false`) |
| POST | `/setup/{client_id}/brand-voice/generate` | Yes | `draft_brand_voice` | Draft guide returned for review, **not saved**. 409 `profile_required` without an approved profile. 1 generation |
| PUT | `/setup/{client_id}/brand-voice` | Yes | `approve_brand_voice` | Human-approved guide `{voice_description, vocabulary_include[≤30], vocabulary_exclude[≤30], example_sentence}` written into the profile |
| POST | `/setup/{client_id}/strategy-lens` | Yes | `run_strategy_lens` | 201. Runs the panel, saves a `strategy_lens` asset (latest via `GET /assets?kind=strategy_lens`). 1 generation |
| GET | `/setup/{client_id}/accounts` | Yes | `client_accounts` | This client's **connected** accounts `{id, platform, account_handle, display_name, status, connected_at}` plus `oauth: {platform: {configured, scopes}}` |

Write rules (`services/setup_profile.py`): approving the intake writes only `target_audience`, `competitor_differentiation`, `tone_attributes.register` (other tone keys merged) and `client.website_url` when a URL is given; approving a brand voice writes only `voice_description`, the two vocabulary lists and the one `voice_north_star` entry in `example_posts`. `style_rules`, `emoji_policy` and `client.settings` are never touched. Tests: `tests/test_setup_profile.py`.

## Post Studio (Queue / Calendar actions)
**Status**: [LIVE]
**File**: `backend/src/agency/routers/post_studio.py` · service `services/post_studio.py` · agent `agents/post_writer.py` (worker tier)
<!-- verified: 260923 -->

No router prefix; paths are spelled out because they share `/content` with `routers/content.py` (none collides). **Everything created or rewritten here is `draft` (Pending)** — moderation runs at approve time as for every other path. Platforms: `twitter`, `linkedin`, `instagram`, `facebook`, `tiktok` (keys of `PLATFORM_CHAR_LIMITS`; others → 422 `unsupported_platform`).

| Method | Path | Auth | Handler | Purpose |
|--------|------|------|---------|---------|
| GET | `/post-studio/channels?client_id=` | Yes | `channels` | `{connected: [platform], supported: [platform]}` |
| POST | `/content/generate` | Yes | `generate` | 201. `{client_id, platform, context_note? (≤280), planned_for?}` → one new Pending draft (`metadata.source = "queue_generate"`). 1 generation |
| POST | `/content` | Yes | `create_manual` | 201. Hand-written post `{client_id, platform, body, planned_for?}` → Pending (`metadata.source = "calendar_manual"`). Free. 422 `over_limit` past the platform limit |
| POST | `/content/{content_id}/regenerate` | Yes | `regenerate` | Rewrite in place (same id). Only `draft`/`rejected`, else 409 `invalid_status`; stays/returns to `draft`, drops `metadata.moderation`, bumps `regenerate_count`. 1 generation |
| POST | `/content/{content_id}/creative-brief` | Yes | `creative_brief` | A written designer brief stored at `metadata.creative_brief` — **no image is made**; text and status untouched. 409 `published_locked` on a published post. 1 generation |
| DELETE | `/content/{content_id}` | Yes | `delete` | 204. Hard-deletes any unpublished post; 409 `published_locked` for a published one |

- `planned_for` is written to `scheduled_at` on a **draft** as its *planned* day (Calendar "Add post" / "Fill with AI"). It is only a plan: the scheduler publishes `status == "scheduled"` rows only, and a draft reaches `scheduled` solely via approve → schedule.
- Generate / manual post for an archived client → 409 `client_archived`.
- **Server-side cancel:** generate, regenerate and creative brief check `request.is_disconnected()` after the model returns; if the caller has gone, they return 409 `{"code": "cancelled"}` and save/charge nothing. (Amplify and the Create screens do not do this — there, Cancel only stops the browser waiting.)
- Tests: `tests/test_post_studio.py`.

## Create › Content
**Status**: [LIVE]
**File**: `backend/src/agency/routers/create_content.py` · validators `services/create_content.py` · agent `agents/create_content.py` (worker tier) · web research `services/competitor_research.py`
<!-- verified: 260923 -->

Long-form output with no platform and no publish path — copied, exported as Markdown, or taken into the queue through Amplify. All require a brand profile (409 `brand_profile_required`) and follow the [generator contract](#shared-generator-contract-260923). Each returns the saved asset.

| Method | Path | Auth | Handler | Purpose |
|--------|------|------|---------|---------|
| POST | `/create/content/blog` | Yes | `generate_blog` | `{client_id}` → `blog_post`. Reads keywords of the client's last 100 blog posts so it does not repeat a target keyword |
| POST | `/create/content/comparison` | Yes | `generate_comparison` | `{client_id, competitor_name}` → `comparison_page`, grounded in Exa web research |
| POST | `/create/content/niche-scan` | Yes | `generate_niche_scan` | `{client_id, competitor_names[2–5 after cleaning]}` → `niche_scan` with a `gapRecommendation` |
| POST | `/create/content/video-script` | Yes | `generate_video_script` | `{client_id}` → `video_script` |
| POST | `/create/content/niche-scan/{asset_id}/blog` | Yes | `generate_blog_from_gap` | Blog post written from a scan's gap; new `blog_post` with `source_asset_id` = the scan. 422 if not a scan / no gap |
| POST | `/create/content/blog/{asset_id}/ai-seo` | Yes | `optimize_for_ai_search` | Merges an `aiSeoPack` into an existing blog post's payload (never replaces the draft). 409 `already_optimized`; 422 if not a blog / empty body |

Comparison and niche scan store `payload.webResearch = {status, reason, retrievedAt, sources}` and a `sourcesNote`: when `EXA_API_KEY` is unset or the search fails, the record says `unavailable` with the reason — the output is never presented as researched. Tests: `tests/test_create_content.py`.

## Create › Email
**Status**: [LIVE]
**File**: `backend/src/agency/routers/create_email.py` · `services/create_kits.py` · agent `agents/lifecycle_email.py` (worker tier)
<!-- verified: 260923 -->

| Method | Path | Auth | Handler | Purpose |
|--------|------|------|---------|---------|
| POST | `/create/email/generate` | Yes | `generate` | `{client_id, campaign_type: welcome\|onboarding\|reengagement\|update\|milestone}` → `email_campaign` asset. Brand profile required. 1 generation |

**Nothing is sent** — CampaignForge drafts; the human sends from their own email tool. List/delete via `/assets?kind=email_campaign`. Tests: `tests/test_create_email_launch.py`.

## Create › Launch
**Status**: [LIVE]
**File**: `backend/src/agency/routers/create_launch.py` · `services/create_kits.py` · agent `agents/launch_pr.py`
<!-- verified: 260923 -->

| Method | Path | Auth | Handler | Purpose |
|--------|------|------|---------|---------|
| GET | `/create/launch/prfaq?client_id=` | Yes | `get_prfaq` | `{prfaq}` — the client's current stress-test, or `null` |
| POST | `/create/launch/prfaq` | Yes | `run_prfaq` | `{client_id}` → run / re-run the PRFAQ stress-test (**brain** tier). Replaces the previous one at `client.settings.prfaq` (+ `generated_at`). 1 generation |
| POST | `/create/launch/generate` | Yes | `generate` | `{client_id, mode: launch_kit\|community_kit\|outreach_pitch}` → asset of that kind (worker tier). 1 generation |

- The PRFAQ is not a list item: one current critique per client, stored in `client.settings.prfaq` beside `campaign_focus`. It deliberately does **not** read the campaign focus (its prompt drops all Setup extras).
- A `launch_kit` is written with the stored PRFAQ in hand when one exists; its payload records `prfaq_addressed: true|false`.
- Drafts only — no Product Hunt, press, Discord/Slack or CRM integration. Brand profile required for all three routes.

## Create › Ads
**Status**: [LIVE]
**File**: `backend/src/agency/routers/create_ads.py` · guardrails `services/ad_guardrails.py` · `services/ad_sets.py` · agent `agents/ads.py`
<!-- verified: 260923 -->

| Method | Path | Auth | Handler | Purpose |
|--------|------|------|---------|---------|
| GET | `/create/ads/spec` | Yes | `spec` | `{limits: AD_LIMITS, meta_cta_options}` — the numbers the checks use, so the UI shows the same ones |
| POST | `/create/ads/generate` | Yes | `generate` | `{client_id, network: google\|meta}` → one `ad_set` asset. 1 generation |

- Generation on the `ad_copy` tier; then code guardrails (`validate_ad_assets`, `find_trademark_risks` against competitor names from the client's comparison pages / niche scans, `find_personal_attribute_risks`) and an advisory **brain**-tier moderation pass that fails open with status `unavailable`. Problems are reported on the asset, never "fixed" by truncation.
- Google limits are hard (headline 30, description 90, path 15, sitelink 25, callout 25); Meta's are *visible* thresholds far below the hard caps.
- **Copy and structure only:** no ad account is connected, nothing creates a campaign or spends money, and no endpoint returns a CTR, CPC or ROAS. No brand-profile gate. Tests: `tests/test_ad_guardrails.py`, `tests/test_create_ads.py`.

## Inbox
**Status**: [LIVE] (X mentions); LinkedIn comments only with `LINKEDIN_INBOX_SCOPE`
**File**: `backend/src/agency/routers/inbox.py` · service `services/inbox.py` · agent `agents/inbox_reply.py` (worker tier) · table [`inbox_item_state`](database-schema.md#inboxitemstate)
<!-- verified: 260923 -->

| Method | Path | Auth | Handler | Purpose |
|--------|------|------|---------|---------|
| GET | `/inbox?client_id=&refresh=` | Yes | `get_inbox` | Live items + per-account status: `{client_id, accounts: [{account_id, platform, handle, status, message, retry_after, reply_supported, …}], items, dms: {available: false, reason}}` |
| PATCH | `/inbox/items/state` | Yes | `set_item_state` | `{client_id, item_id: "<platform>:<id>", read?, handled?}` — triage state only |
| POST | `/inbox/suggest-reply` | Yes | `suggest_reply` | `{client_id, platform, type, author, text}` → `{suggestion, needs_personal_attention}`. Message fenced as untrusted data. 1 generation |
| POST | `/inbox/reply` | Yes | `send_reply` | **Posts for real.** `{client_id, account_id, item_id, text (≤3000), override}` |

- Items are **read live, never stored** (X: `GET /2/users/:id/mentions`; LinkedIn: comments on posts CampaignForge itself published, via `content_piece.metadata.post_id`). Cached per account in memory (120 s OK, 30 s error, `retry_after` when rate-limited); `refresh=true` bypasses the cache at most every 20 s.
- Per-account `status`: `ok`, `not_connected`, `needs_reconnect`, `api_access_denied` (X plan/credits, or LinkedIn without the scope — the platform's own text in `message`), `rate_limited`, `unsupported` (e.g. Facebook), `error`. **DMs are never read** (X needs `dm.read`, not requested; LinkedIn has no messaging API for this app).
- An expired X token is refreshed with the stored refresh token; `GET /inbox` commits so the rotated token persists.
- **Reply safety:** the account is selected by `org_id` **and** `client_id`; the target item must be present in that account's own fetched inbox (404 otherwise — never trusted from the request); moderation runs first (409 `moderation_flagged` unless `override`, recorded as `override_by`); 409 `reply_unsupported` where replying is not available (LinkedIn without the scope). Success and failure both write `audit_log` (`inbox.reply` / `inbox.reply_failed`); failure → 502 `{code: "reply_failed", status, message}`. On success the item is marked read + handled with `reply_id` / `reply_url`.
- Tests: `tests/test_inbox.py`.

## Insights
**Status**: [LIVE]
**File**: `backend/src/agency/routers/insights.py` · `services/insights.py` · agent `agents/advocacy.py` (worker tier)
<!-- verified: 260923 -->

| Method | Path | Auth | Handler | Purpose |
|--------|------|------|---------|---------|
| GET | `/insights/summary?client_id=` | Yes | `insights_summary` | Funnel, `by_platform`, `publish`, `moderation`, `quality_signal`, `engagement`, `recommendations`, `thresholds`. No LLM call |
| POST | `/insights/advocacy` | Yes | `create_advocacy` | `{client_id}` → review request + case-study outline + proof line, saved as an `advocacy` asset (payload includes the `facts` it was given). 1 generation; tracks `advocacy_generated` |

- Every ratio is gated on a minimum sample (`MIN_SAMPLE = 3`): below it the value is `{"status": "insufficient_data", "value": null, "n", "needed"}`; `thresholds` lists every recommendation rule with its progress so the UI can say what data is missing.
- Quality signal uses `metadata.edited_before_approval`, the moderation record and `moderation_flagged` events; engagement comes only from `analytics_snapshot` rows the platforms returned (`status: unavailable` otherwise).
- Advocacy may cite only the server-supplied `advocacy_facts` (published / created posts, moderation checks, connected platforms, and measured engagement when present). A reply citing any other number is a 502 and nothing is charged or saved.
- Tests: `tests/test_insights_settings.py`.

## Workspace (Settings data per client)
**Status**: [LIVE]
**File**: `backend/src/agency/routers/workspace.py` · `services/activity.py` · `services/workspace_export.py`
<!-- verified: 260923 -->

| Method | Path | Auth | Handler | Purpose |
|--------|------|------|---------|---------|
| GET | `/workspace/activity?client_id=&limit=` | Yes | `activity_log` | Newest-first events (max 50), **derived from real rows** — post created/scheduled/published/failed/rejected, moderation passed/overridden/flagged, account connected, profile updated, asset created, pack generated, campaign created, and `audit_log` entries for this client |
| GET | `/workspace/export?client_id=` | Yes | `export` | Download `campaignforge-<slug>-<date>.json`: client (incl. `settings`), brand profile, connected accounts (**no tokens**), campaigns, posts, creative assets, Amplify packs |
| GET | `/workspace/posting-prefs?client_id=` | Yes | `get_posting_prefs` | `{posting_prefs}` |
| PUT | `/workspace/posting-prefs?client_id=` | Yes | `set_posting_prefs` | `{voice_register?, cadence_per_week? (3\|5\|7\|14)}` → `client.settings.posting_prefs` (+ `updated_at`). Fed to every generator by `brand_prompt_block` |

Every query filters on `org_id` and the org-resolved `client_id`. Tests: `tests/test_insights_settings.py`.

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
| POST | `/publishing/{content_id}/schedule` | Yes | `schedule_content` | Schedule content; body: `scheduled_at`; `approved`/`scheduled` only, else 409 `not_approved`; Instagram/TikTok → 409 `platform_unavailable` |
| GET | `/publishing/calendar` | Yes | `get_calendar` | `start`, `end` (UTC). Default: `scheduled`/`published`, by `scheduled_at`. <!-- verified: 260923 --> `client_id` narrows to one client (no separate ownership check — the query is already `org_id`-filtered, so a foreign id matches nothing); `include_pending=true` adds `draft`/`approved` posts that carry a *planned* day, and `failed` ones. Items now include `hashtags` |

## Team
**Status**: [LIVE]
**File**: `backend/src/agency/routers/team.py`

| Method | Path | Auth | Handler | Purpose |
|--------|------|------|---------|---------|
| GET | `/team` | Yes | `get_team` | List org members |
| POST | `/team/invite` | Yes | `invite_member` | Invite user (temp password; best-effort AgentMail) |
| POST | `/team/{user_id}/resend-invite` | Yes | `resend_member_invite` | Rotate the temp password and re-mail the invite. The only route back when the first invite's email failed — re-POSTing `/team/invite` 400s forever. 403 on self |
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
| GET | `/oauth/{platform}/authorize?client_id=&code_challenge=` | Yes | `get_oauth_url` | `{authorize_url, platform}`. `client_id` optional, org-resolved (404). X requires `code_challenge` (S256, ≤128 chars; 400 without). Blank app id → 501 |
| POST | `/oauth/{platform}/callback` | Yes | `oauth_callback` | Body `{code, client_id, state?, code_verifier?, account_handle?, display_name?}`. Exchanges the code and stores an encrypted `PlatformAccount` |
| DELETE | `/oauth/{platform}/{account_id}` | Yes | `disconnect_platform` | Disconnect (status `disconnected`, tokens cleared) |

<!-- verified: 260923 -->
Platforms: `twitter`, `linkedin`, `facebook`. The redirect URI is `{first CORS_ORIGINS entry}/api/oauth/{platform}/callback` — a **page** in the Next.js app (`app/(dashboard)/api/oauth/[platform]/callback/page.tsx`), which posts code + state + verifier here.

- **Signed state** (`services/oauth_state.py`): HS256 JWT, 15-minute expiry, claims `typ=oauth_state`, `org`, `plt`, optional `cid`, random `nonce`. Signed with a key **derived** from `JWT_SECRET` (`"{JWT_SECRET}:oauth_state"`), so a state can never verify as a login token or vice versa. The callback rejects (400) a state that is invalid/expired, for another platform, another org, or another client than the body's `client_id`.
- **PKCE for X** (`PKCE_PLATFORMS = {"twitter"}`): the browser generates the verifier, keeps it in `sessionStorage` and sends only the challenge to `authorize`; the callback requires `code_verifier` (400 without) and authenticates to X's token endpoint with HTTP Basic.
- **Scopes:** X `tweet.read tweet.write users.read offline.access`; LinkedIn `openid profile w_member_social`, **plus `LINKEDIN_INBOX_SCOPE`** when set (deduplicated); Facebook `pages_manage_posts,pages_read_engagement`. `oauth_platform_status()` reports `{configured, scopes}` per platform for `GET /setup/{client_id}/accounts`.
- Tenancy: the body `client_id` is resolved against `org_id` *before* the token exchange (404).
- Known gaps: `state` is verified only when it is sent — a callback without one still succeeds (the in-app page always sends it). `account_handle` / `display_name` fall back to the placeholder `{platform}_user`; the real handle is never fetched from the platform.

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

<!-- verified: 260923 --> Since 260923 `POST /inbox/reply` writes `inbox.reply` / `inbox.reply_failed` entries — the first caller of `log_action`. The empty-result `reason` string in `routers/audit.py` ("no route writes audit entries") is therefore stale; an empty table still returns `status: unavailable`, which remains fair since nothing else is audited.

## Product Analytics
**Status**: [LIVE]
**File**: `backend/src/agency/routers/product_analytics.py`

| Method | Path | Auth | Handler | Purpose |
|--------|------|------|---------|---------|
| POST | `/events` | Yes | `ingest_events` | Batch browser events (≤50). Only `session_started`, `session_ended`, `page_view`, `feature_used` are accepted; others counted as rejected |
| GET | `/beta-metrics` | Yes | `get_beta_metrics` | Beta plan §7 metrics for the caller's org (`window_days`, 1–180, default 28) |

**Total: 133 endpoints across 35 routers** (counted from `@router.*` decorators, 260923) — every router file in `routers/` is mounted in `main.py` with prefix `/api/v1`. Added 260923: `assets` 4, `setup` 7, `post_studio` 6, `create_content` 6, `create_email` 1, `create_launch` 3, `create_ads` 2, `inbox` 4, `insights` 2, `workspace` 4, plus 3 on `clients`.

Note: `product_analytics.py` and `post_studio.py` declare no router prefix — `product_analytics`' two routes land at `/api/v1/events` and `/api/v1/beta-metrics`; `post_studio` spells out `/content/...` and `/post-studio/...` in full. `slack.py` and `webhooks_config.py` both nest under the `/integrations` path without being part of `integrations.py`.
