# Platform Integrations
<!-- verified: 260923 -->

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

<!-- verified: 260923 -->
**Connecting** (260923): real provider redirects from Setup › Accounts — signed `state`, PKCE for X, return page at `/api/oauth/{platform}/callback`. See [api-endpoints.md › OAuth](api-endpoints.md#oauth).

**Reading (Inbox, 260923)** — `services/inbox.py`, live, nothing stored except triage state:

| Platform | Reads | Replies | Needs |
|----------|-------|---------|-------|
| X / Twitter | [LIVE] mentions timeline `GET /2/users/:id/mentions` | [LIVE] `POST /2/tweets` reply | `tweet.read users.read` (held) **and** an X API plan that allows reads (402/403 surface as `api_access_denied`). Access tokens auto-refreshed |
| LinkedIn | [LIVE, gated] comments on posts CampaignForge published | [LIVE, gated] comment | `LINKEDIN_INBOX_SCOPE` (`r_member_social` or `r_organization_social`, granted only to approved apps); `LINKEDIN_API_VERSION` header. Commenter names are not resolvable with these scopes |
| Facebook / others | — (`unsupported`) | — | — |
| DMs (any) | not read | — | X `dm.read` not requested; LinkedIn has no messaging API for this app |

**Metrics caveat:** the live analytics path still runs through `services/analytics_fetcher.py`, which persists all-zero snapshots. `services/platform_metrics.py` holds the real fetchers but has no callers yet — "Meta (Facebook & Instagram)" as a headline capability claim currently overstates Instagram on both publish and metrics.

## Stripe
**Status**: [LIVE]
**File**: `backend/src/agency/services/billing.py`

Checkout sessions, webhook processing, subscription lifecycle. See [billing.md](billing.md).

## AgentMail
**Status**: [LIVE]
**File**: `backend/src/agency/services/email_service.py`

Transactional email. All outbound mail goes through `send_email()`, which sends from a **shared sender inbox** — `AGENTMAIL_FROM_EMAIL`, default `alerts@intelliforge.tech`. An org that has its own `organization.agentmail_inbox_id` overrides the shared sender per message; nothing provisions per-org inboxes yet, so in practice everything sends from the shared address.

**The AgentMail send limit is per *organization*, not per app.** The free plan allows 100 sends/day across the whole AgentMail account, and `alerts@intelliforge.tech` is shared with other IntelliForge senders — the daily "IntelliForge Morning Briefing" newsletter among them. A bulk blast can therefore exhaust the quota before a single team invite is attempted, and every send for the rest of the window returns 429 while the key, the domain and the sender inbox are all perfectly healthy. `_describe_send_failure` names this case explicitly instead of returning the raw `ApiError` header dump. If transactional mail needs to be independent of bulk mail, it needs its own AgentMail organization or a paid plan — a separate inbox on the same account does not help, because the quota is account-scoped.

**`AGENTMAIL_API_KEY` must be set as a Fly secret, and the key must be live.** Because `send_email()` degrades quietly by contract, neither failure is visible from the server's health: the API looks fine and accounts are still created, but no mail leaves. Production ran with the secret entirely absent and every team invite logged `team_invite_email_not_sent reason='AgentMail is not configured'` while the UI reported the account created. A key that is present but revoked fails differently and just as quietly — `ensure_sender_inbox()` gets a 403 and returns None. Check `GET /api/v1/health/email` and read `can_send`; `configured` only means a key string exists.

`send_email()` **never raises and never lies**: it returns `SendResult(sent, reason, inbox_id)`, and a missing key, an unverified domain, or an AgentMail outage yields `sent=False` with a reason. Callers must surface `sent` honestly rather than claiming an email went out — `POST /api/v1/team/invite` returns `email_sent: bool` for exactly this reason.

The sender inbox is resolved once per process (get, then create on 404) and memoized. **Creating it requires the domain to be VERIFIED in AgentMail**; an unverified domain is the usual cause of `sent=False`.

Consumers: team invitations (`routers/team.py`).

Env vars: `AGENTMAIL_API_KEY`, `AGENTMAIL_FROM_EMAIL`, `AGENTMAIL_DEFAULT_DOMAIN` (fallback domain, only read when `AGENTMAIL_FROM_EMAIL` is a bare username).

In production the key is a Fly secret: `fly secrets set AGENTMAIL_API_KEY=... -a campaignforge-api`.

## Clerk
**Status**: [LIVE]
**File**: `backend/src/agency/dependencies.py`

JWT verification, user info fetching, auto-provisioning. See [auth-and-rbac.md](auth-and-rbac.md).

## LLM Providers
**Status**: [LIVE]
**File**: `backend/src/agency/services/llm_provider.py`

Seven providers. Selection is **per tier, not per agent** — agents only ever call `get_brain_llm()`, `get_worker_llm()`, `get_ad_copy_llm()`, or `get_lite_llm()`. Per tier, the first provider in `LLM_PROVIDER_ORDER` with a key becomes primary and the rest attach as LangChain `.with_fallbacks()`.

| Provider | Kind | Env Var | Default model |
|----------|------|---------|---------------|
| Anthropic | native SDK | `ANTHROPIC_API_KEY` | `claude-sonnet-5` (`claude-haiku-4-5` for ad copy and lite) |
| Google | native SDK | `GOOGLE_API_KEY` / `GEMINI_API_KEY` | `gemini-2.5-flash` |
| OpenAI | OpenAI-compatible | `OPENAI_API_KEY` | `gpt-4o-mini` |
| NVIDIA NIM | OpenAI-compatible | `NVIDIA_NIM_API_KEY` | `deepseek-ai/deepseek-v4-flash` |
| OpenRouter | OpenAI-compatible | `OPENROUTER_API_KEY` | `openai/gpt-oss-120b` |
| Bonsai | OpenAI-compatible | `BONSAI_API_KEY` | `gpt-4o-mini` |
| Groq | OpenAI-compatible | `GROQ_API_KEY` | `llama-3.3-70b-versatile` |

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

HTTP fetch of target URL + LLM-powered brand profile extraction. No external API key beyond LLM provider. The fetch is restricted to public addresses by `services/url_safety.py`.

## Exa — Search
**Status**: [LIVE] <!-- verified: 260923 -->
**File**: `backend/src/agency/services/exa_client.py`

Shared Exa client, keyed by `EXA_API_KEY`. Callers: `services/trends.py`, `agents/competitive_intel.py`, and (260923) `services/competitor_research.py` for Create › Content comparison pages and niche scans. With no key or a failed search, callers return an explicit `unavailable` record with the reason — output is never presented as web-researched when it was not. (This section previously said `[PLANNED]`; that was stale since Phase 1.)
