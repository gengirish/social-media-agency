# Services
<!-- verified: 260328 -->

Business logic layer in `backend/src/agency/services/`.

## LLM Provider
**Status**: [LIVE]
**File**: `services/llm_provider.py`

Three-tier LLM routing:

| Function | Role | Model |
|----------|------|-------|
| `get_brain_llm()` | Orchestrator, QA | Claude Sonnet (Anthropic) |
| `get_worker_llm(temperature=0.7)` | Strategy, SEO, Content | Gemini 2.0 Flash (Google) |
| `get_ad_copy_llm()` | Ad variants | Claude (Anthropic) |
| `_get_fallback_llm(temperature=0.7)` | Fallback | GPT-4o-mini (OpenAI) |

Env vars: `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `OPENAI_API_KEY`

## Billing Service
**Status**: [LIVE]
**File**: `services/billing.py`

Stripe subscription management. Singleton: `billing = BillingService()`.

### Plan Config

| Tier | Price | Clients | Posts/mo |
|------|-------|---------|----------|
| free | $0 | 2 | 30 |
| starter | $49/mo | 5 | 100 |
| growth | $149/mo | 15 | 500 |
| agency | $399/mo | unlimited | unlimited |

### Methods

- `create_checkout_session(db, org_id, plan_tier, success_url, cancel_url)` — Stripe Checkout
- `handle_webhook(db, event)` — Routes: checkout.completed, invoice.paid, subscription.cancelled/updated
- `get_subscription(db, org_id)` — Current subscription + limits
- `check_quota(db, org_id, resource="posts")` — Quota enforcement
- `get_plans()` — Plan catalog

## Publishing
**Status**: [LIVE]
**File**: `services/publishing.py`

Platform publishing. Singleton: `publisher = PlatformPublisher()`.

- `publish(platform, content, credentials)` — Routes to platform-specific handler; HTTP layer uses `_with_http_retries` (up to 3 attempts with backoff on transient `httpx` errors)
- `_decrypt_token(encrypted)` — Token decryption stub (passthrough until Fernet/production wiring)
- `_publish_twitter(content, credentials)` — X/Twitter API v2
- `_publish_linkedin(content, credentials)` — LinkedIn UGC API
- `_publish_facebook(content, credentials)` — Facebook Graph API
- `_publish_instagram(content, credentials)` — Placeholder/stub

## Scheduler
**Status**: [LIVE]
**File**: `services/scheduler.py`

Asyncio-based content scheduler. Singleton: `scheduler = SchedulerEngine()`. Started from `main.py` startup event.

- `start()` / `stop()` — Lifecycle
- `schedule_content(db, content_id, scheduled_at)` — Set publish time
- `get_calendar(db, org_id, start, end)` — Calendar view
- `_process_due_content()` — Minute loop, publishes content where `scheduled_at <= now`

## Brand Learning
**Status**: [LIVE]
**File**: `services/brand_learning.py`

- `update_brand_learnings(db, client_id, analytics_data)` — Merges learnings into `BrandProfile.tone_attributes["learned"]`

Called automatically after campaign completion in `_persist_campaign_results`. Stores: best_performing_topics, optimal_posting_times, engagement_multipliers, topic_engagement_index, platform_benchmarks.

## Magic Brief
**Status**: [LIVE]
**File**: `services/magic_brief.py`

- `extract_brand_from_url(url)` — Fetches URL content, sends to LLM for brand profile extraction (voice, tone, audience, etc.)

## Team Service
**Status**: [LIVE]
**File**: `services/team.py`

- `invite_team_member(db, org_id, email, role, invited_by)` — Create user with temp password
- `list_team_members(db, org_id)` — All org members
- `update_member_role(db, org_id, user_id, new_role)` — Role change
- `check_permission(user_role, action)` — Role permission matrix

## API Keys
**Status**: [LIVE]
**File**: `services/api_keys.py`

- `create_api_key(db, org_id, name, permissions)` — Create key; returns plaintext once
- `list_api_keys(db, org_id)` — Metadata only (no secrets)
- `revoke_api_key(db, org_id, key_id)` — Soft deactivation
- `validate_api_key(db, raw_key)` — Hash-based lookup; used by API key auth middleware for programmatic access

## White Label
**Status**: [LIVE]
**File**: `services/white_label.py`

- `get_white_label(db, org_id)` — Get branding config
- `upsert_white_label(db, org_id, data)` — Create or update

## Reporting
**Status**: [LIVE]
**File**: `services/reporting.py`

- `generate_report_data(db, client_id, org_id, period)` — Client report data

## Notifications
**Status**: [LIVE]
**File**: `services/notifications.py`

- `create_notification()` — In-app notification creation

## Trends
**Status**: [LIVE]
**File**: `services/trends.py`

- `get_trending_topics(platform)` — Platform trending topics

## Analytics Fetcher
**Status**: [LIVE]
**File**: `services/analytics_fetcher.py`

- `fetch_content_metrics()`, `get_content_analytics()`, `get_client_analytics_summary()`

## Cross Learning
**Status**: [LIVE]
**File**: `services/cross_learning.py`

- `get_industry_benchmarks()`, `get_cross_campaign_insights()`

## Knowledge Base
**Status**: [LIVE]
**File**: `services/knowledge_base.py`

RAG knowledge retrieval from marketing skills library.

## Image Generation
**Status**: [LIVE]
**File**: `services/image_generation.py`

- `generate_social_image()` — via fal.ai

## Slack Integration
**Status**: [LIVE]
**File**: `services/slack_integration.py`

Slack messaging.

## Webhook Dispatcher
**Status**: [LIVE]
**File**: `services/webhook_dispatcher.py`

Event webhook dispatch.

## Client Acquisition
**Status**: [LIVE]
**File**: `services/client_acquisition.py`

Prospect outreach generation.

## Ad Optimization
**Status**: [LIVE]
**File**: `services/ad_optimization.py`

Bid optimization analysis (LLM-assisted).

## Audit
**Status**: [LIVE]
**File**: `services/audit.py`

- `log_action()` — Audit trail logging
