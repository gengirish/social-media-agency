# Services
<!-- verified: 260817 -->

Business logic layer in `backend/src/agency/services/` — 23 modules. Routers stay thin; business logic lives here.

## LLM Provider
**Status**: [LIVE]
**File**: `services/llm_provider.py`

Three-tier, provider-agnostic LLM routing. Agents call only these three:

| Function | Tier | Role | Temperature |
|----------|------|------|-------------|
| `get_brain_llm()` | `brain` | Orchestrator, QA | 0.3 |
| `get_worker_llm(temperature=0.7)` | `worker` | Strategy, SEO, Content | 0.7 |
| `get_ad_copy_llm()` | `ad_copy` | Ad variants | 0.8 |

Seven providers, each enabled purely by setting its API key:

| Provider | Kind | Default model |
|----------|------|---------------|
| `anthropic` | native SDK | `claude-sonnet-5` (`claude-haiku-4-5` for ad copy and lite) |
| `google` | native SDK | `gemini-2.5-flash` |
| `openai` | OpenAI-compatible | `gpt-4o-mini` |
| `nvidia` | OpenAI-compatible | `deepseek-ai/deepseek-v4-flash` |
| `openrouter` | OpenAI-compatible | `openai/gpt-oss-120b` |
| `bonsai` | OpenAI-compatible | `gpt-4o-mini` |
| `groq` | OpenAI-compatible | `llama-3.3-70b-versatile` |

> Groq's base URL is `https://api.groq.com/openai/v1` — note the `/openai` segment; the usual `/v1` shape 404s every call. Groq also retires model ids faster than the other gateways, and a stale id surfaces as a 404 that reads like a bad key: change `GROQ_MODEL` before suspecting the key.

- `resolution_chain(tier)` — providers to try, best first
- `resolve_provider(tier)` — the primary
- `get_llm(tier, temperature=None)` — primary with the rest attached via `.with_fallbacks()`
- `describe_providers()` — diagnostics for `GET /health/llm`; never returns keys

Order comes from `LLM_PROVIDER_ORDER` (default `anthropic,google,openai,nvidia,openrouter,bonsai,groq`). `LLM_{TIER}_PROVIDER` pins a tier and disables its fallbacks. `LLM_{TIER}_MODEL` overrides the primary's model only. With nothing configured, `get_llm()` raises naming the variables to set.

Env vars: `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY` (`GEMINI_API_KEY` accepted as alias), `OPENAI_API_KEY`, `NVIDIA_NIM_API_KEY`, `OPENROUTER_API_KEY`, `BONSAI_API_KEY`, `GROQ_API_KEY`. **A blank key disables that provider** — adding a key is the whole activation step.

## Billing Service
**Status**: [LIVE]
**File**: `services/billing.py`

Stripe subscription management. Singleton: `billing = BillingService()`.

### Plan Config

Source of truth is `PLAN_CONFIG` in `services/billing.py`.

| Tier | Price | Clients | Posts/mo | Campaigns/mo |
|------|-------|---------|----------|--------------|
| free | $0 | 1 | 30 | 5 (no publishing) |
| starter | $4900 (¢) | 3 | 200 | 20 |
| growth | $14900 (¢) | 10 | 1000 | 9999 (unlimited) |
| agency | $39900 (¢) | 999 (unlimited) | 99999 (unlimited) | 9999 (unlimited) |

"Unlimited" tiers use large sentinel numbers rather than nulls — quota checks are plain integer comparisons.

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
- `_decrypt_token(encrypted)` — Real decryption via `decrypt_token`; legacy plaintext rows fall back with a warning
- `_publish_twitter(content, credentials)` — X/Twitter API v2 **[LIVE]**
- `_publish_linkedin(content, credentials)` — LinkedIn UGC API **[LIVE]**
- `_publish_facebook(content, credentials)` — Facebook Graph API **[LIVE]**
- `_publish_instagram(content, credentials)` — **[STUB]** returns an explicit "not available yet" message. Text-only posts are unsupported; a real implementation needs the Meta Graph container+publish flow with media

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
**Status**: [STUB]
**File**: `services/trends.py`

- `get_trending_topics(platform)` — returns entries from a hardcoded `PLATFORM_TRENDS` dict keyed by platform. **No live data source is wired.** Backs `GET /campaigns/trends` and the Analytics → Trends tab, both of which therefore display invented topics.

## Analytics Fetcher
**Status**: [STUB]
**File**: `services/analytics_fetcher.py`

- `fetch_content_metrics()` — resolves the content piece and connected `PlatformAccount`, then writes an `AnalyticsSnapshot` with **all metrics hardcoded to zero**. The comment at the metrics dict marks where platform API calls belong.
- `get_content_analytics()`, `get_client_analytics_summary()` — read back whatever snapshots exist

Because zeroed snapshots are persisted, downstream reads cannot distinguish "no engagement" from "never fetched". See [Platform Metrics](#platform-metrics) for the intended replacement.

## Platform Metrics
**Status**: [IN PROGRESS] — implemented but **not wired to any caller**
**File**: `services/platform_metrics.py`

Real platform metric fetchers, written to replace the zeros in `analytics_fetcher`. Nothing in `src/` or `tests/` imports this module yet.

| Function | State |
|----------|-------|
| `fetch_twitter_metrics(post_id, access_token)` | Real — X v2 metrics |
| `fetch_linkedin_metrics(post_id, access_token, org_urn=None)` | Real — LinkedIn stats |
| `fetch_facebook_metrics(post_id, access_token)` | Real — Graph insights |
| `fetch_instagram_metrics(post_id, access_token)` | [STUB] — returns `unavailable` |
| `fetch_post_metrics(platform, post_id, access_token, *, page_id=None, token_is_encrypted=False)` | Dispatcher |

Design contract: every failure path returns an explicit `unavailable` result via `_unavailable(reason)` rather than raising, **so callers never persist fabricated data**. Retries go through `_with_retries`. Integration therefore requires the caller to *skip* writing a snapshot on `unavailable` — not to store zeros as `analytics_fetcher` does today.

## Cross Learning
**Status**: [LIVE]
**File**: `services/cross_learning.py`

- `get_industry_benchmarks()`, `get_cross_campaign_insights()`

## Knowledge Base
**Status**: [STUB]
**File**: `services/knowledge_base.py`

- `_load_skills_library()` — loads the marketing skills corpus
- `retrieve_knowledge(query, k=3)` — **keyword overlap scoring, not vector similarity.** The module docstring says "vector-indexed" and the function docstring says pgvector is used "in production"; neither is true. No embeddings are computed and pgvector is not installed. Wired into the strategy agent.

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

## Product Analytics
**Status**: [LIVE]
**File**: `services/product_analytics.py`

Backs the beta metrics dashboard (`docs/beta-testing-plan.md` §7).

- `track(db, ...)` — write on the caller's session; caller commits
- `track_detached(...)` — own session, never raises (pipeline tasks, middleware)
- `beta_metrics(db, org_id, window_days)` — assembles the full §7 table
- Individual metrics: `time_to_first_campaign`, `campaign_outcomes`, `agent_step_dropoff`, `feature_adoption`, `session_duration`, `return_rate`, `errors_by_endpoint`
- `record_request()` / `request_rate_snapshot()` — in-memory request counters; reset on process restart

`CLIENT_WRITABLE_EVENTS` allowlists the four events the browser may write, so pipeline and error counts stay server-authored.
