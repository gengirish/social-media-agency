# Feature Changelog

Chronological record of feature changes. Newest first.

---

## 260324 — End-to-End Multi-Agent Pipeline Fixes

- **Fixed**: SSE stream auth — accepts JWT via `?token=` query param for EventSource compatibility
- **Added**: AgentRun tracking — inserts DB row per agent node completion during campaign pipeline
- **Added**: Human review UI — approve/revise buttons in LiveAgentDashboard with PATCH to backend
- **Added**: Brand learning wiring — `update_brand_learnings()` called on campaign completion
- **Changed**: Analytics page — replaced "Coming Soon" with real KPI dashboard (stats, content pipeline, campaign status, agent metrics)
- **Changed**: Settings page — replaced static cards with tabbed UI (General, Platforms, API Keys, Notifications)
- **Changed**: Agent stream client — uses Clerk token parameter instead of localStorage
- **Fixed**: CI pipeline — removed `continue-on-error: true` so failures are caught
- **Changed**: Team invite — honest response message + best-effort AgentMail email
- **Added**: Full feature documentation — all 10 feature doc files created from codebase scan

## 260324 — Clerk Authentication Integration

- **Added**: Clerk JWT verification (RS256 + JWKS) in backend `get_current_user`
- **Added**: Auto-provisioning of users/orgs on first Clerk login
- **Added**: `ClerkTokenSync` component to wire Clerk tokens into API client
- **Added**: Clerk middleware for frontend route protection
- **Added**: E2E test auth via Clerk sign-in tokens (bypasses instance-level MFA)
- **Changed**: `get_org_id` fallback to user dict for Clerk sessions

## 260324 — Feature Documentation Initialized

- **Added**: `feature-docs` skill — Living documentation system
- **Added**: `docs/features/` directory — Central location for all feature documentation
