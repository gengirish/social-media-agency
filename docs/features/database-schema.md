# Database Schema
<!-- verified: 260818 -->

PostgreSQL (Neon serverless) via SQLAlchemy async. **21 tables** (20 without pgvector).

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
| `settings` | JSONB | |
| `is_active` | Boolean | |
| `created_at` / `updated_at` | DateTime(tz) | |

**Relationships**: `brand_profile` (one-to-one), `campaigns` (one-to-many)

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
| `metadata_` | JSONB | |
| `media_urls` | JSONB | |
| `ai_generated` | Boolean | |
| `status` | String | draft, approved, scheduled, published |
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
Enterprise audit trail. Fields: `org_id`, `user_id`, `action`, `resource_type`, `resource_id`, `details` JSONB, `ip_address`, `created_at`.

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
               ├── Client (many) ──┬── BrandProfile (one)
               │                   ├── Campaign (many) ──┬── ContentPiece (many)
               │                   │                     ├── AgentRun (many)
               │                   │                     └── Workflow (one)
               │                   └── PlatformAccount (many)
               ├── WhiteLabel (one)
               ├── CampaignTemplate (many)
               └── ApiKey (many)
```
