# Frontend Components
<!-- verified: 260328 -->

Reusable components in `frontend/src/components/`.

## DashboardContent
**Status**: [LIVE]
**File**: `components/dashboard-content.tsx`

Dashboard home stats grid. Fetches `api.getStats()` and displays 6 metric cards: total clients, campaigns, content pieces, agent runs, campaigns running, content drafts.

## NotificationsBell
**Status**: [LIVE]
**File**: `components/notifications-bell.tsx`

Bell icon with unread count badge. Dropdown notification panel. Polls every 30s. Mark read / mark all read.

## ClerkTokenSync
**Status**: [LIVE]
**File**: `components/clerk-token-sync.tsx`

Registers Clerk's `getToken()` function with the API client via `setClerkTokenGetter()`. Mounted in root layout. No visual output.

## LiveAgentDashboard
**Status**: [LIVE]
**File**: `components/agents/live-agent-dashboard.tsx`

Real-time agent pipeline visualization for campaign execution.

### Props
- `campaignId: string` — Campaign to stream
- `onComplete?: () => void` — Callback when pipeline finishes
- `onWaitingHuman?: () => void` — Callback when review needed

### Features
- Connects to SSE stream via `connectAgentStream()` with Clerk token
- 7 agent cards with status indicators (pending → running → complete/error/waiting)
- Progress bar (0–100%)
- **Human review panel**: Appears when pipeline pauses at `human_review` node
  - "Approve & Continue" — sends `{decision: "approved"}` via PATCH
  - "Request Revisions" — sends `{decision: "revise_content"}` via PATCH
  - Verifies response before updating local state
- Activity log showing timestamped agent events

### Agent Pipeline Display

| Agent | Icon | Description |
|-------|------|-------------|
| Orchestrator | Brain | Parsing brief & planning |
| Strategy | Target | Campaign strategy |
| SEO Research | Search | Keywords & optimization |
| Content Writer | PenTool | Creating content |
| Ad Copy | Megaphone | Ad variants |
| Human Review | UserCheck | Awaiting approval |
| QA / Brand | Shield | Quality check |

## Library Modules

### `lib/api.ts`
API client singleton. Uses `NEXT_PUBLIC_API_URL` (default `http://localhost:8001`). Clerk token injected via `setClerkTokenGetter()`. **45+ methods** covering backend endpoints (dashboard, content, campaigns, integrations, notifications, portal helpers, etc.).

### `lib/agent-stream.ts`
`connectAgentStream(campaignId, token, onEvent, onError?)` — Opens EventSource to SSE endpoint with JWT in query param. Returns teardown function.

### `lib/utils.ts`
`cn(...inputs)` — `clsx` + `tailwind-merge` for class name composition.
