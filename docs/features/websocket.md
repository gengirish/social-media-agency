# Real-time Features
<!-- verified: 260921 -->

> **Filename note:** this file is called `websocket.md` for historical reasons. There is no WebSocket in this codebase — the realtime layer is SSE, documented accurately below.

## Server-Sent Events (SSE)
**Status**: [LIVE]
**File**: `backend/src/agency/routers/campaigns.py`

No WebSocket implementation. Real-time communication uses SSE via `sse-starlette`.

### Endpoint

`GET /api/v1/campaigns/{campaign_id}/stream?token=<JWT>`

Auth via query param (EventSource cannot send headers). Verifies Clerk JWKS then legacy HS256 JWT; no token → 401, invalid → 401, no `org_id` in the token → 400. The campaign must belong to the token's org → otherwise 404. If no pipeline queue exists for the campaign (not started, already finished, or started on another machine/process), the stream sends one `error` event — "No active pipeline for this campaign." — and ends.

### Event Types

| Type | Agent | Meaning |
|------|-------|---------|
| `step_complete` | node name | Agent finished; includes progress % |
| `waiting_human` | `human_review` | Pipeline paused for human review |
| `complete` | `pipeline` | All agents finished successfully |
| `error` | node/pipeline | Error occurred |
| `heartbeat` | — | Sent when no event arrives for 120s |

`step_start` and `step_update` appear in the `AgentStreamEvent.type` comment (`models/schemas.py`) and the frontend type union (`lib/api.ts`), and `LiveAgentDashboard` handles `step_start` — but **the backend never emits either**. Agents move from pending straight to complete in the UI.

### Architecture

- In-memory `asyncio.Queue` per campaign (`_campaign_streams` dict)
- Pipeline task pushes events; SSE endpoint pops from queue
- Queue cleaned up on `complete` or `error`
- One consumer per queue: `queue.get()` removes the event, so two tabs streaming the same campaign split the events between them rather than each seeing all of them
- Production: should migrate to Redis pub/sub for multi-instance support

### Frontend Client

`connectAgentStream(campaignId, token, onEvent, onError?)` in `frontend/src/lib/agent-stream.ts`. Opens `EventSource`, parses JSON, auto-closes on terminal events.
