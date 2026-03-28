# Platform Integrations
<!-- verified: 260324 -->

## Social Publishing
**Status**: [LIVE]
**File**: `backend/src/agency/services/publishing.py`

| Platform | API | Status |
|----------|-----|--------|
| X / Twitter | v2 API | [LIVE] |
| LinkedIn | UGC API | [LIVE] |
| Facebook | Graph API | [LIVE] |
| Instagram | Graph API | [PLANNED] — stub only |

Publishing is triggered via `POST /api/v1/publishing/{content_id}/publish` or automatically by the scheduler when `scheduled_at` arrives.

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

| Provider | Use | Env Var |
|----------|-----|---------|
| Anthropic (Claude) | Orchestrator, QA, Ad Copy | `ANTHROPIC_API_KEY` |
| Google (Gemini Flash) | Strategy, SEO, Content | `GOOGLE_API_KEY` |
| OpenAI (GPT-4o-mini) | Fallback | `OPENAI_API_KEY` |

## Magic Brief
**Status**: [LIVE]
**File**: `backend/src/agency/services/magic_brief.py`

HTTP fetch of target URL + LLM-powered brand profile extraction. No external API key beyond LLM provider.
