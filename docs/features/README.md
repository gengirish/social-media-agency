# Feature Documentation
<!-- verified: 260324 -->

Living documentation of all platform features. Updated whenever the codebase changes.

## Quick Stats
- **API Endpoints**: —
- **Database Tables**: 10
- **Services**: 8
- **Background Workers**: 4
- **Frontend Pages**: 12+
- **Platform Integrations**: 5

> Stats are approximate until first full scan. Run the `feature-docs` skill to populate.

## Documents

| Document | Description | Last Updated |
|----------|-------------|-------------|
| [api-endpoints.md](api-endpoints.md) | REST API routes | — |
| [database-schema.md](database-schema.md) | Tables and relationships | — |
| [services.md](services.md) | Business logic layer | — |
| [workers.md](workers.md) | Celery background jobs | — |
| [integrations.md](integrations.md) | Social platform connectors | — |
| [websocket.md](websocket.md) | Real-time features | — |
| [frontend-pages.md](frontend-pages.md) | UI routes and pages | — |
| [frontend-components.md](frontend-components.md) | Reusable UI components | — |
| [auth-and-rbac.md](auth-and-rbac.md) | Auth, roles, permissions | — |
| [billing.md](billing.md) | Stripe billing features | — |
| [changelog.md](changelog.md) | Chronological change log | 260324 |

## How This Works

These docs are maintained by the **`feature-docs`** skill (`.cursor/skills/feature-docs/`). The skill:

1. Scans source code for routers, models, services, pages, etc.
2. Compares against what's documented here
3. Updates the matching doc file with current state
4. Appends changes to the changelog

### Keeping Docs Current

After any code change that adds, modifies, or removes a feature:
- Ask the agent to "update feature docs" or reference the `feature-docs` skill
- The skill will detect what changed and update only the relevant files

### Status Labels

| Label | Meaning |
|-------|---------|
| `[LIVE]` | Feature is implemented and active |
| `[IN PROGRESS]` | Feature is partially implemented |
| `[PLANNED]` | Feature is designed but not yet built |
| `[DEPRECATED]` | Feature is scheduled for removal |
