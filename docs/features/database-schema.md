# Database Schema
<!-- verified: 260923 -->

PostgreSQL (Neon serverless) via SQLAlchemy async. **24 tables** (23 without pgvector). `repurpose_pack` added 260921; `creative_asset` and `inbox_item_state` added 260923.

> ### Pending Neon migrations — Cadence full parity (260923)
>
> Run by hand on Neon, **in this order**, before deploying the backend from `feat/cadence-parity`:
>
> 1. `db/migrations/260923_creative_asset.sql` — creates `creative_asset` (+ index). Without it `/api/v1/assets/*` and every Create screen fail with `UndefinedTable`.
> 2. `db/migrations/260923_amplify_asset_source.sql` — adds `repurpose_pack.source_asset_id` (FK → `creative_asset`, so it needs step 1). Without it `/api/v1/amplify/*` fails with `UndefinedColumn`.
> 3. `db/migrations/260923_inbox.sql` — creates `inbox_item_state`. Without it `/api/v1/inbox` fails with `UndefinedTable`.
>
> All three are additive and safe to re-run (`IF NOT EXISTS`). `db/init.sql` already carries them for fresh databases.
>
> ### Pending Neon migration (260925)
>
> 4. `db/migrations/260925_workspace_profile.sql` — adds `organization.workspace_profile`
>    (nullable, CHECK-constrained). Without it `GET /api/v1/billing/plans` fails with
>    `UndefinedColumn` and the pricing page cannot load. Independent of 1–3.

**File**: `backend/src/agency/models/tables.py`

Schema is raw SQL in `db/init.sql` (+ `db/seed.sql`), **not** Alembic migrations, despite `alembic` being a dependency.

> ### A schema change takes THREE edits, not two
>
> 1. `db/init.sql` — for databases created from scratch.
> 2. `backend/src/agency/models/tables.py` — what the ORM emits in every `SELECT`.
> 3. `db/migrations/<YYMMDD>_<name>.sql` — a dated, forward-only, additive script.
>
> **`init.sql` runs only against an empty database.** Docker-compose executes it on
> first boot and a fresh Neon branch gets it once; after that it is never replayed.
> Skipping step 3 means the change reaches local dev and CI, passes review, and
> silently never lands in production.
>
> This is not hypothetical. On 260818 the live Neon branch was missing four tables
> (`notification`, `webhook`, `webhook_delivery`, `knowledge_embedding`) and two
> `white_label` columns that `tables.py` had declared for weeks. Because SQLAlchemy
> names every mapped column in its `SELECT`, a single absent column takes out the
> whole route: the client portal returned 500 on `white_label.portal_enabled`, and
> every notifications route failed on a table that did not exist. Both were marked
> `[LIVE]` in this file at the time. Closed by `db/migrations/260818_schema_catchup.sql`.
>
> Verify any environment with the model-vs-database diff: compare
> `Base.metadata.tables` against `information_schema.columns`. Zero drift in both
> directions is the only acceptable result.

## Organization
**Status**: [LIVE]

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `name` | String | Not unique — never resolve an org by it |
| `slug` | String(64) **UNIQUE**, nullable | Portal identity. `/api/v1/portal/{org_slug}` is unauthenticated, so this is the only column it resolves on. Null = that org has no portal (fail-closed). Added 260817 — run `db/migrations/260817_org_slug.sql` on existing databases |
| `domain` | String | Not unique |
| `settings` | JSONB | |
| `agentmail_inbox_id` | String | AgentMail integration |
| `agentmail_email` | String | AgentMail address |
| `is_active` | Boolean | Default true |
| `created_at` | DateTime(tz) | |
| `updated_at` | DateTime(tz) | |

## User
**Status**: [LIVE]

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `org_id` | UUID FK → Organization | |
| `email` | String | Unique |
| `password_hash` | String | `"clerk-managed"` for Clerk users |
| `full_name` | String | |
| `role` | String | admin, member, viewer |
| `is_active` | Boolean | |
| `created_at` | DateTime(tz) | |

## Subscription
**Status**: [LIVE]

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `org_id` | UUID FK → Organization | |
| `stripe_customer_id` | String | |
| `stripe_subscription_id` | String | |
| `plan_tier` | String | free, starter, growth, agency |
| `clients_limit` | Integer | |
| `posts_limit` | Integer | |
| `posts_used` | Integer | |
| `generations_used` | Integer NOT NULL, default 0 | Amplify packs generated this billing period (1 pack = 1 generation). Reset to 0 with `posts_used` on `invoice.paid`. Added 260921 |
| `generations_limit` | Integer, nullable | Set from `PLAN_CONFIG[tier]["generations_limit"]` on provisioning and every plan change. NULL falls back to the tier's value (`billing.generations_limit_for`). Added 260921 |
| `period_start` | DateTime(tz) | |
| `period_end` | DateTime(tz) | |
| `status` | String | |
| `created_at` | DateTime(tz) | |

## Client
**Status**: [LIVE]

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `org_id` | UUID FK → Organization | |
| `brand_name` | String | |
| `industry` | String | |
| `website_url` | String | |
| `contact_email` | String | |
| `logo_url` | String | |
| `description` | Text | |
| `settings` | JSONB | Setup extras, see below |
| `is_active` | Boolean | |
| `created_at` / `updated_at` | DateTime(tz) | |

**Relationships**: `brand_profile` (one-to-one), `campaigns` (one-to-many)

<!-- verified: 260923 -->
**`settings` keys** (no schema change; each writer reassigns the dict so SQLAlchemy sees the JSONB change, and merges rather than replaces):

| Key | Shape | Written by |
|-----|-------|-----------|
| `campaign_focus` | `{description (≤300), set_at}` | `PUT/DELETE /clients/{id}/campaign-focus` |
| `prfaq` | PRFAQ stress-test payload + `generated_at` | `POST /create/launch/prfaq` (replaced on re-run) |
| `posting_prefs` | `{voice_register?, cadence_per_week?, updated_at}` | `PUT /workspace/posting-prefs` |

`brand_context.load_brand_context` passes the whole dict to generators as `brand["setup"]`; `brand_prompt_block` reads `campaign_focus` and `posting_prefs`.

## BrandProfile
**Status**: [LIVE]

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `client_id` | UUID FK → Client | Unique |
| `org_id` | UUID FK → Organization | |
| `voice_description` | Text | |
| `tone_attributes` | JSONB | Includes `learned` sub-key from brand_learning |
| `target_audience` | Text | |
| `style_rules` | JSONB (array) | |
| `vocabulary_include` / `exclude` | JSONB (array) | |
| `emoji_policy` | String | moderate, liberal, none |
| `competitor_differentiation` | Text | |
| `created_at` / `updated_at` | DateTime(tz) | |

<!-- verified: 260923 -->
Setup › Profile (`services/setup_profile.py`) writes the intake into `target_audience`, `competitor_differentiation` and `tone_attributes.register` (one of four fixed registers), and the approved Brand Voice guide into `voice_description`, the vocabulary lists and one `example_posts` entry of kind `voice_north_star`. It never touches `style_rules` or `emoji_policy`.

## Campaign
**Status**: [LIVE]

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `client_id` | UUID FK → Client | |
| `org_id` | UUID FK → Organization | |
| `name` | String | |
| `objective` | String | |
| `channels` | Text[] | |
| `start_date` / `end_date` | Date | |
| `budget` | JSONB | `{total_usd: N}` |
| `agent_plan` | JSONB | Orchestrator execution plan |
| `tags` | JSONB | |
| `status` | String | running, completed, failed |
| `created_at` / `updated_at` | DateTime(tz) | |

## ContentPiece
**Status**: [LIVE]

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `campaign_id` / `client_id` / `org_id` | UUID FK | |
| `agent_run_id` | UUID FK → AgentRun | Nullable |
| `content_type` | String | social_post, google_ad, meta_ad, etc. |
| `platform` | String | twitter, linkedin, instagram, etc. |
| `title` / `body` | String / Text | |
| `hashtags` | JSONB | |
| `metadata_` | JSONB | Keys written by the gate and Amplify: `moderation` (`status`, `issues`, `override_by`, `at`), `amplify_pack_id`, `source_id`, `angle`; by publishing: `post_url`, `publish_error` |
| `media_urls` | JSONB | |
| `ai_generated` | Boolean | |
| `status` | String | `draft` (shown as **Pending** in the UI), `approved`, `scheduled`, `published`, `failed`, `rejected`. Transitions are gated — see [api-endpoints.md › Approval gate](api-endpoints.md#approval-gate) |
| `performance_score` | Float | |
| `scheduled_at` / `published_at` | DateTime(tz) | |
| `created_at` / `updated_at` | DateTime(tz) | |

## AgentRun
**Status**: [LIVE]

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `campaign_id` | UUID FK → Campaign | |
| `org_id` | UUID FK → Organization | |
| `agent_name` | String | orchestrate, strategise, seo_research, etc. |
| `input_summary` | Text | |
| `output` | Text | JSON stringified agent output |
| `tokens_used` | Integer | |
| `duration_ms` | Integer | |
| `model_used` | String | |
| `cost_usd` | Numeric | |
| `status` | String | completed, failed |
| `created_at` | DateTime(tz) | |

## Workflow
**Status**: [LIVE]

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `campaign_id` | UUID FK → Campaign | Unique |
| `org_id` | UUID FK → Organization | |
| `current_node` | String | |
| `status` | String | running, completed |
| `total_duration_ms` | Integer | |
| `total_cost_usd` | Numeric | |
| `created_at` / `completed_at` | DateTime(tz) | |

## RepurposePack
**Status**: [LIVE]
<!-- verified: 260921 -->

One row per generated Amplify pack (`routers/amplify.py`). Atoms are **not** stored here: preview returns them, commit writes the kept ones to `content_piece` as drafts whose `metadata.amplify_pack_id` points back (FK by convention, not a column).

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `org_id` | UUID FK → Organization, NOT NULL | `ON DELETE CASCADE` in `init.sql` |
| `client_id` | UUID FK → Client, NOT NULL | `ON DELETE CASCADE` in `init.sql` |
| `source_content_id` | UUID FK → ContentPiece, nullable | `ON DELETE SET NULL`. Null when the source was pasted text |
| `source_text` | Text, nullable | Pasted source; null when `source_content_id` is set |
| `source_asset_id` | UUID FK → CreativeAsset, nullable | `ON DELETE SET NULL`. Set when the source was a saved Create-screen asset. Added 260923 (`260923_amplify_asset_source.sql`) <!-- verified: 260923 --> |
| `platforms` | JSONB NOT NULL, default `[]` | Platforms requested |
| `atom_count` | Integer NOT NULL, default 0 | Atoms returned by preview |
| `committed_count` | Integer NOT NULL, default 0 | Atoms written by commit; `> 0` blocks a second commit |
| `created_by` | UUID FK → users, nullable | `ON DELETE SET NULL` |
| `created_at` | DateTime(tz) | |

Index `idx_repurpose_pack_org_created` on `(org_id, created_at DESC)` — the history list.

`tables.py` declares the `org_id`/`client_id` FKs without `ondelete`; the cascade exists only in SQL. Harmless for queries, but the ORM does not know about it.

**Migration:** `db/migrations/260921_amplify.sql` — adds both `subscription` columns, backfills `generations_limit` by tier (`free` 10, `starter` 50, `growth` 250, `agency` 9999 — must match `PLAN_CONFIG`), and creates `repurpose_pack` + its index. Additive and re-runnable. **Run it by hand on Neon before deploying the backend that ships `routers/amplify.py`**, or `/api/v1/amplify/*` and `/billing/subscription` fail with `UndefinedColumn` / `UndefinedTable`.

## CreativeAsset
**Status**: [LIVE]
<!-- verified: 260923 -->

Kept output of a Create-screen generator — one row per generation (Content, Email, Launch, Ads, Insights advocacy, Setup strategy lens). **Social posts never live here**; they are `content_piece` drafts so the approval gate applies. Read/rename/delete via `/assets`.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `org_id` | UUID FK → Organization, NOT NULL | `ON DELETE CASCADE` |
| `client_id` | UUID FK → Client, NOT NULL | `ON DELETE CASCADE` |
| `kind` | VARCHAR(40) NOT NULL | Closed set, enforced in code by `services/creative_assets.py::ASSET_KINDS` (not a DB enum) |
| `title` | VARCHAR(500) NOT NULL, default `''` | |
| `payload` | JSONB NOT NULL, default `{}` | The kind's JSON shape |
| `source_asset_id` | UUID FK → CreativeAsset, nullable | `ON DELETE SET NULL`. E.g. a blog post written from a niche scan's gap |
| `created_by` | UUID FK → users, nullable | `ON DELETE SET NULL` |
| `created_at` / `updated_at` | DateTime(tz) | |

Index `idx_creative_asset_org_client_kind` on `(org_id, client_id, kind, created_at DESC)`.

**Migration:** `db/migrations/260923_creative_asset.sql`.

## InboxItemState
**Status**: [LIVE]
<!-- verified: 260923 -->

What a human did with one Inbox item. Inbox items are read live from X / LinkedIn and **never stored**; only this triage state is.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `org_id` | UUID FK → Organization, NOT NULL | `ON DELETE CASCADE` |
| `client_id` | UUID FK → Client, NOT NULL | `ON DELETE CASCADE` |
| `item_key` | VARCHAR(255) NOT NULL | `"<platform>:<platform item id>"` |
| `is_read` | Boolean NOT NULL, default false | |
| `handled` | Boolean NOT NULL, default false | |
| `reply_id` / `reply_url` | VARCHAR(255) / Text, nullable | Set when a reply was sent from CampaignForge |
| `updated_by` | UUID FK → users, nullable | `ON DELETE SET NULL` |
| `updated_at` | DateTime(tz) | |

Unique `(org_id, client_id, item_key)`.

**Migration:** `db/migrations/260923_inbox.sql`.

## Other Tables

### PlatformAccount [LIVE]
Social platform OAuth credentials per client. Fields: platform, account_handle, display_name, encrypted tokens, followers_count, status.

### AnalyticsSnapshot [LIVE]
Per-content per-platform metrics. Fields: date, impressions, reach, engagement, clicks, shares, likes, followers_delta, extra JSONB.

### ContentComment [LIVE]
Review comments on content pieces. Fields: content_id, user_id, body text.

### WhiteLabel [LIVE]
Org white-label branding config. One per org. Fields: branding strings/text/bool. Also `portal_enabled` (boolean) and `email_from_name` for client portal and outbound labeling.

### CampaignTemplate [LIVE]
Reusable campaign templates (public + org-specific). Fields: name, category, objective_template, channels, content_directives JSONB, is_public, uses_count.

### ApiKey [LIVE]
Org API keys with hashed storage. Fields: name, key_hash, key_prefix, permissions text[], is_active, last_used_at.

### Notification [LIVE]
In-app notification system. Fields: `user_id`, `org_id`, `type`, `title`, `body`, `data` JSONB, `read` (boolean), `created_at`.

### AuditLog [LIVE]
Enterprise audit trail. Fields: `org_id`, `user_id`, `action`, `resource_type`, `resource_id`, `details` JSONB, `ip_address`, `created_at`. First writer (260923): `POST /inbox/reply` (`inbox.reply`, `inbox.reply_failed`, `resource_type = "inbox_item"`). The Settings activity log reads rows whose `details.client_id` matches.

### ProductEvent [LIVE]
Product-analytics event stream behind `GET /beta-metrics`. Fields: `org_id` (nullable), `user_id` (nullable), `session_id`, `name`, `category` (`pipeline` | `session` | `feature` | `error`), `path`, `campaign_id`, `duration_ms`, `properties` JSONB, `occurred_at`, `created_at`.

`org_id`/`user_id` are nullable so failures on unauthenticated requests are still recorded. Distinct from `AuditLog`: audit answers *who changed what*, this answers *how the product is used*. Indexed on `(org_id, occurred_at)`, `(name, occurred_at)`, `(user_id, occurred_at)`, `campaign_id`, `session_id`.

## Entity Relationships

```
Organization ──┬── User (many)
               ├── Subscription (one)
               ├── Notification (many)
               ├── AuditLog (many)
               ├── ProductEvent (many)
               ├── RepurposePack (many) ── Client (one), ContentPiece source (0..1), CreativeAsset source (0..1)
               ├── Client (many) ──┬── BrandProfile (one)
               │                   ├── CreativeAsset (many) ── CreativeAsset source (0..1)
               │                   ├── InboxItemState (many)
               │                   ├── Campaign (many) ──┬── ContentPiece (many)
               │                   │                     ├── AgentRun (many)
               │                   │                     └── Workflow (one)
               │                   └── PlatformAccount (many)
               ├── WhiteLabel (one)
               ├── CampaignTemplate (many)
               └── ApiKey (many)
```
