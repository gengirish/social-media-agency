# Platform Integrations
<!-- verified: 260817 -->

## Social Publishing
**Status**: [LIVE]
**File**: `backend/src/agency/services/publishing.py`

| Platform | Publish | Metrics |
|----------|---------|---------|
| X / Twitter | [LIVE] v2 API | [IN PROGRESS] `platform_metrics.fetch_twitter_metrics` — written, unwired |
| LinkedIn | [LIVE] UGC API | [IN PROGRESS] `fetch_linkedin_metrics` — written, unwired |
| Facebook | [LIVE] Graph API | [IN PROGRESS] `fetch_facebook_metrics` — written, unwired |
| Instagram | [STUB] returns "not available yet" | [STUB] returns `unavailable` |

Publishing is triggered via `POST /api/v1/publishing/{content_id}/publish` or automatically by the scheduler when `scheduled_at` arrives. OAuth tokens are stored encrypted on `PlatformAccount` and decrypted at publish time.

**Metrics caveat:** the live analytics path still runs through `services/analytics_fetcher.py`, which persists all-zero snapshots. `services/platform_metrics.py` holds the real fetchers but has no callers yet — "Meta (Facebook & Instagram)" as a headline capability claim currently overstates Instagram on both publish and metrics.

## Stripe
**Status**: [LIVE]
**File**: `backend/src/agency/services/billing.py`

Checkout sessions, webhook processing, subscription lifecycle. See [billing.md](billing.md).

## AgentMail
**Status**: [IN PROGRESS]
**File**: `backend/src/agency/routers/team.py`

Best-effort email sending for team invitations when `AGENTMAIL_API_KEY` is configured and org has `agentmail_inbox_id` set.

Env vars: `AGENTMAIL_API_KEY`, `AGENTMAIL_DEFAULT_DOMAIN`

## Clerk
**Status**: [LIVE]
**File**: `backend/src/agency/dependencies.py`

JWT verification, user info fetching, auto-provisioning. See [auth-and-rbac.md](auth-and-rbac.md).

## LLM Providers
**Status**: [LIVE]
**File**: `backend/src/agency/services/llm_provider.py`

Six providers. Selection is **per tier, not per agent** — agents only ever call `get_brain_llm()`, `get_worker_llm()`, or `get_ad_copy_llm()`. Per tier, the first provider in `LLM_PROVIDER_ORDER` with a key becomes primary and the rest attach as LangChain `.with_fallbacks()`.

| Provider | Kind | Env Var | Default model |
|----------|------|---------|---------------|
| Anthropic | native SDK | `ANTHROPIC_API_KEY` | `claude-sonnet-4-20250514` (haiku for ad copy) |
| Google | native SDK | `GOOGLE_API_KEY` / `GEMINI_API_KEY` | `gemini-2.5-flash` |
| OpenAI | OpenAI-compatible | `OPENAI_API_KEY` | `gpt-4o-mini` |
| NVIDIA NIM | OpenAI-compatible | `NVIDIA_NIM_API_KEY` | `deepseek-ai/deepseek-v4-flash` |
| OpenRouter | OpenAI-compatible | `OPENROUTER_API_KEY` | `openai/gpt-oss-120b` |
| Bonsai | OpenAI-compatible | `BONSAI_API_KEY` | `gpt-4o-mini` |

A blank key disables a provider. `GET /api/v1/health/llm` (authenticated) reports the resolved provider, model, and fallback chain per tier without exposing key material. See [services.md](services.md#llm-provider) for tier/temperature detail.

## fal.ai — Image Generation
**Status**: [LIVE]
**File**: `backend/src/agency/services/image_generation.py`

AI social image generation via `POST /api/v1/content/{content_id}/generate-image`.

Env var: `FAL_API_KEY`

## Slack
**Status**: [LIVE]
**File**: `backend/src/agency/services/slack_integration.py`, `routers/slack.py`

Slack bot with event and slash-command handlers at `POST /api/v1/integrations/slack/events` and `/commands`, both signature-verified.

## Magic Brief
**Status**: [LIVE]
**File**: `backend/src/agency/services/magic_brief.py`

HTTP fetch of target URL + LLM-powered brand profile extraction. No external API key beyond LLM provider.

## Exa — Search
**Status**: [PLANNED]

`EXA_API_KEY` is defined in `config.py` and `.env.example`, but no service reads it. `services/trends.py` returns hardcoded topics instead of querying Exa.
