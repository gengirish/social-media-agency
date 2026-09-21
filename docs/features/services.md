# Services
<!-- verified: 260921 -->

Business logic layer in `backend/src/agency/services/` — 27 modules (260921). Routers stay thin; business logic lives here.

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

| Tier | Price | Clients | Posts/mo | Campaigns/mo | Amplify packs/period |
|------|-------|---------|----------|--------------|----------------------|
| free | $0 | 1 | 30 | 5 (no publishing) | 10 |
| starter | $4900 (¢) | 3 | 200 | 20 | 50 |
| growth | $14900 (¢) | 10 | 1000 | 9999 (unlimited) | 250 |
| agency | $39900 (¢) | 999 (unlimited) | 99999 (unlimited) | 9999 (unlimited) | 9999 (unlimited) |

"Unlimited" tiers use large sentinel numbers rather than nulls — quota checks are plain integer comparisons.

### Methods

- `create_checkout_session(db, org_id, plan_tier, success_url, cancel_url)` — Stripe Checkout
- `handle_webhook(db, event)` — Routes: checkout.completed, invoice.paid, subscription.cancelled/updated
- `get_subscription(db, org_id)` — Current subscription + limits; also `generations_used` and `generations_limit` (the row's values, not the tier default)
- `generations_limit_for(sub)` (module function) — the org's Amplify allowance: the row's `generations_limit`, or the tier's `PLAN_CONFIG` value when it is NULL, then the free tier — never unlimited
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

## Moderation
**Status**: [LIVE]
**File**: `services/moderation.py`

Pre-approval moderation (product rule 3).

- `moderate_content(body, platform, brand_context, *, hashtags=None) -> ModerationResult` — `status` `passed`/`flagged`/`unavailable`, `issues: [{severity, message}]`, `llm_checked`. Never raises.
- Deterministic checks: `check_char_limit` (`PLATFORM_CHAR_LIMITS`: X 280, LinkedIn 3000, Instagram/TikTok 2200, Facebook 63206 — measured on `published_text()`, i.e. with the hashtags the publisher appends) and `check_excluded_vocabulary` (brand `vocabulary_exclude`, whole-word, case-insensitive).
- Judgement check via `get_brain_llm()` (policy risk, unverifiable/guaranteed claims, fabricated scarcity, brand vocabulary/voice), capped at `MODERATION_TIMEOUT_SECONDS`. **Fails open**: error/timeout/unparseable → `unavailable`, logs `moderation_unavailable`.
- `load_brand_context(db, client_id, org_id)` — client + brand profile, both filtered on `org_id`.

## Content Approval
**Status**: [LIVE]
**File**: `services/content_approval.py`

The approval gate; raises `ContentGateError(status_code, detail)` which routers map to HTTP errors.

- `approve_content_piece(db, piece, *, org_id, override, user_id)` — `draft`/`rejected` only; moderates; records `metadata.moderation`; commits. Used by `/content/{id}/approve` and the portal (override always false).
- `ensure_publishable(piece)` — `approved`/`scheduled` only; used by schedule and publish-now.
- `apply_content_edit(piece, ...)` — PATCH logic: refuses gated statuses; body/hashtag edits reset approved/scheduled content to `draft`.

## Repurpose (Amplify helpers)
**Status**: [LIVE]
**File**: `services/repurpose.py`
<!-- verified: 260921 -->

Pure helpers for Amplify — no DB, no LLM — so the guards are unit-tested in isolation (`tests/test_repurpose.py`).

- `REPURPOSE_ANGLES` — closed taxonomy: `hook`, `how-to`, `contrarian`, `story`, `data-point`, `question`, `behind-the-scenes`, `listicle`. `MAX_ATOMS = len(REPURPOSE_ANGLES)` (8). `ANGLE_DEFINITIONS` spells each out for the prompt.
- `PLATFORM_CHAR_LIMITS` — derived from `agents/content_writer.PLATFORM_GUIDELINES[*]["max_length"]` (not restated), keys `twitter`, `linkedin`, `instagram`, `facebook`, `tiktok`. `PLATFORM_FORMATS` — per-platform format guidance for the prompt.
- `plan_atoms(platforms, max_atoms, used_angles)` — assigns `(platform, angle)` pairs before the LLM call; platforms rotate, angles already used for the same source go last.
- `validate_atoms(raw, platforms, max_atoms)` → `AtomValidation(kept, dropped)` — drops non-objects, unrequested platforms, unknown or repeated angles, empty bodies, and bodies whose `rendered_length` exceeds the platform limit; hashtags are stripped of `#`, de-duplicated, capped at 10.
- `rendered_length(body, hashtags)` — body + blank line + every hashtag as `#tag`.
- `jaccard(a, b)` / `is_angle_duplicate(candidate, recent, threshold=0.6)` — stopword-filtered token-set overlap; a reworded-duplicate catch, not semantic similarity.
- `drip_schedule(n, start, per_week=5)` — `n` suggested 09:00 slots, one per day at most, starting the day after `start`. **Not called by any endpoint or UI** yet.

## Amplify Agent
**Status**: [LIVE]
**File**: `agents/amplify.py`
<!-- verified: 260921 -->

Not a graph node — called directly by `routers/amplify.py`.

- `generate_amplify_atoms(*, source_text, requests, brand, campaign_brief=None) -> AmplifyResult(atoms, dropped)` — one `get_worker_llm(0.8)` call (`AMPLIFY_TEMPERATURE`). Worker, not `lite`: whether eight atoms are genuinely different angles *is* the judgement.
- Prompt: system rules (ground every atom in the source, no invented claims/numbers, one angle each, hashtags in their own array, no outcome promises), `format_brand_context(brand)` (empty fields omitted; up to 3 example posts truncated to 600 chars), optional campaign brief, source excerpt (first 6000 chars), the used angles' definitions, and the numbered requests with format + hard limit.
- Output is never trusted: atoms whose `(platform, angle)` was not requested are dropped as off-plan, then `validate_atoms` runs. Drops are logged as `amplify_atoms_dropped`.
- LLM errors propagate; the router maps them to 502 without charging quota.

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

Amplify adds two server-authored `feature`-category events, written from `routers/amplify.py` and **not** client-writable: `amplify_pack_generated` (properties: `pack_id`, `requested`, `atoms`, `dropped`, `platforms`, `source`) and `amplify_pack_committed` (`pack_id`, `committed`, `generated`, `angles`).
