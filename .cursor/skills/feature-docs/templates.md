# Feature Documentation Templates

Use these templates when creating or updating feature doc files.

---

## API Endpoints (`api-endpoints.md`)

```markdown
# API Endpoints
<!-- verified: YYMMDD -->

## Authentication (`/api/v1/auth`)

| Method | Path | Purpose | Auth | Request Body | Response |
|--------|------|---------|------|-------------|----------|
| POST | `/api/v1/auth/login` | User login | No | `LoginRequest` | `TokenResponse` |
| POST | `/api/v1/auth/signup` | Register org | No | `SignupRequest` | `UserResponse` |

**File**: `backend/src/agency/routers/auth.py`

---
```

## Database Schema (`database-schema.md`)

```markdown
# Database Schema
<!-- verified: YYMMDD -->

## `organization`
**Status**: [LIVE]
**File**: `backend/src/agency/models/tables.py`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | Unique identifier |
| name | VARCHAR | NOT NULL | Agency name |
| domain | VARCHAR | UNIQUE | Custom domain |
| settings | JSONB | DEFAULT '{}' | Org-level config |
| created_at | TIMESTAMP | NOT NULL | Creation timestamp |

**Relationships**: Has many `users`, `clients`, `subscriptions`

---
```

## Services (`services.md`)

```markdown
# Services
<!-- verified: YYMMDD -->

## ContentService
**Status**: [LIVE]
**File**: `backend/src/agency/services/content_service.py`

### Purpose
Manages content creation, editing, and lifecycle within campaigns.

### Public Methods
| Method | Params | Returns | Description |
|--------|--------|---------|-------------|
| `create_content` | campaign_id, body, platform | `Content` | Create new content piece |
| `update_content` | content_id, updates | `Content` | Update draft content |
| `submit_for_approval` | content_id | `Approval` | Trigger approval workflow |

### Dependencies
- `AIEngine` (content generation)
- `AssetService` (media attachments)
- `ApprovalService` (workflow)

---
```

## Workers (`workers.md`)

```markdown
# Background Workers
<!-- verified: YYMMDD -->

## PublishingWorker
**Status**: [LIVE]
**File**: `backend/src/agency/workers/publishing_worker.py`

### Purpose
Publishes scheduled content to platform accounts at the scheduled time.

### Tasks
| Task | Schedule | Description |
|------|----------|-------------|
| `publish_scheduled_posts` | Every 1 min | Check and publish due posts |
| `retry_failed_posts` | Every 5 min | Retry posts that failed to publish |

### Dependencies
- `PlatformService` (API calls)
- Redis (task queue)

---
```

## Frontend Pages (`frontend-pages.md`)

```markdown
# Frontend Pages
<!-- verified: YYMMDD -->

## Dashboard Routes

| Route | File | Purpose | Auth |
|-------|------|---------|------|
| `/` | `app/(dashboard)/page.tsx` | Overview dashboard | Yes |
| `/clients` | `app/(dashboard)/clients/page.tsx` | Client list | Yes |
| `/campaigns` | `app/(dashboard)/campaigns/page.tsx` | Campaign management | Yes |
| `/content` | `app/(dashboard)/content/page.tsx` | Content library | Yes |
| `/calendar` | `app/(dashboard)/calendar/page.tsx` | Content calendar | Yes |
| `/analytics` | `app/(dashboard)/analytics/page.tsx` | Performance analytics | Yes |

## Auth Routes

| Route | File | Purpose | Auth |
|-------|------|---------|------|
| `/login` | `app/(auth)/login/page.tsx` | Login form | No |
| `/signup` | `app/(auth)/signup/page.tsx` | Registration | No |

---
```

## Changelog (`changelog.md`)

```markdown
# Feature Changelog

Chronological record of feature changes. Newest first.

---

## YYMMDD — Description of Change Batch

- **Added**: `feature-name` — What was introduced
- **Changed**: `feature-name` — What was modified and why
- **Deprecated**: `feature-name` — What's being phased out
- **Removed**: `feature-name` — What was deleted
- **Fixed**: `feature-name` — What bug was resolved

---
```

## README Index (`README.md`)

```markdown
# Feature Documentation
<!-- verified: YYMMDD -->

Living documentation of all platform features. Updated whenever the codebase changes.

## Quick Stats
- **API Endpoints**: XX
- **Database Tables**: XX
- **Services**: XX
- **Background Workers**: XX
- **Frontend Pages**: XX
- **Platform Integrations**: XX

## Documents

| Document | Description | Last Updated |
|----------|-------------|-------------|
| [api-endpoints.md](api-endpoints.md) | REST API routes | YYMMDD |
| [database-schema.md](database-schema.md) | Tables and relationships | YYMMDD |
| [services.md](services.md) | Business logic layer | YYMMDD |
| [workers.md](workers.md) | Celery background jobs | YYMMDD |
| [integrations.md](integrations.md) | Social platform connectors | YYMMDD |
| [websocket.md](websocket.md) | Real-time features | YYMMDD |
| [frontend-pages.md](frontend-pages.md) | UI routes and pages | YYMMDD |
| [frontend-components.md](frontend-components.md) | Reusable UI components | YYMMDD |
| [auth-and-rbac.md](auth-and-rbac.md) | Auth, roles, permissions | YYMMDD |
| [billing.md](billing.md) | Stripe billing features | YYMMDD |
| [changelog.md](changelog.md) | Chronological change log | YYMMDD |

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| ... | ... | ... |

---
```
