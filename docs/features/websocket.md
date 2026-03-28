# Real-time Features
<!-- verified: 260328 -->

## Server-Sent Events (SSE)
**Status**: [LIVE]
**File**: `backend/src/agency/routers/campaigns.py`

No WebSocket implementation. Real-time communication uses SSE via `sse-starlette`.

### Endpoint

`GET /api/v1/campaigns/{campaign_id}/stream?token=<JWT>`

Auth via query param (EventSource cannot send headers). Verifies Clerk JWKS then legacy JWT.

### Event Types

| Type | Agent | Meaning |
|------|-------|---------|
| `step_start` | node name | Agent started processing |
| `step_complete` | node name | Agent finished; includes progress % |
| `waiting_human` | `human_review` | Pipeline paused for human review |
| `complete` | `pipeline` | All agents finished successfully |
| `error` | node/pipeline | Error occurred |
| `heartbeat` | — | Keep-alive (every 120s timeout) |

### Architecture

- In-memory `asyncio.Queue` per campaign (`_campaign_streams` dict)
- Pipeline task pushes events; SSE endpoint pops from queue
- Queue cleaned up on `complete` or `error`
- Production: should migrate to Redis pub/sub for multi-instance support

### Frontend Client

`connectAgentStream(campaignId, token, onEvent, onError?)` in `frontend/src/lib/agent-stream.ts`. Opens `EventSource`, parses JSON, auto-closes on terminal events.
