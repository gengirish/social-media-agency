# Scan Targets — Where to Look for Feature Changes

Patterns and grep queries for detecting features across the codebase.

## Backend — API Endpoints

**Location**: `backend/src/agency/routers/*.py`

```bash
# Find all route decorators
rg "@router\.(get|post|put|patch|delete)" backend/src/agency/routers/
```

**Document in**: `docs/features/api-endpoints.md`
**Format**: `METHOD /api/v1/path — description`

## Backend — Database Models

**Location**: `backend/src/agency/models/tables.py`

```bash
# Find all SQLAlchemy model classes
rg "class \w+\(.*Base\)" backend/src/agency/models/
```

**Document in**: `docs/features/database-schema.md`
**Format**: Table name, columns, relationships, constraints

## Backend — Pydantic Schemas

**Location**: `backend/src/agency/models/schemas.py`

```bash
# Find all Pydantic models
rg "class \w+\(.*BaseModel\)" backend/src/agency/models/schemas.py
```

**Document in**: `docs/features/api-endpoints.md` (request/response shapes)

## Backend — Services

**Location**: `backend/src/agency/services/*.py`

```bash
# Find all service classes and public methods
rg "class \w+Service" backend/src/agency/services/
rg "async def [a-z]" backend/src/agency/services/
```

**Document in**: `docs/features/services.md`

## Backend — Workers (Celery Tasks)

**Location**: `backend/src/agency/workers/*.py`

```bash
# Find all Celery task definitions
rg "@(app|celery)\.task|@shared_task" backend/src/agency/workers/
```

**Document in**: `docs/features/workers.md`

## Backend — Platform Integrations

**Location**: `backend/src/agency/integrations/*.py`

```bash
# Find platform connector classes
rg "class \w+Connector|class \w+Integration" backend/src/agency/integrations/
```

**Document in**: `docs/features/integrations.md`

## Backend — WebSocket Handlers

**Location**: `backend/src/agency/websocket/*.py`

```bash
# Find WebSocket route handlers
rg "@router\.websocket|async def websocket" backend/src/agency/websocket/
```

**Document in**: `docs/features/websocket.md`

## Backend — Middleware

**Location**: `backend/src/agency/middleware/*.py`

```bash
rg "class \w+Middleware" backend/src/agency/middleware/
```

**Document in**: `docs/features/auth-and-rbac.md` (auth middleware) or `docs/features/services.md` (other)

## Backend — Config / Env Vars

**Location**: `backend/src/agency/config.py`, `.env.example`

```bash
# Find all settings fields
rg ":\s*str|:\s*int|:\s*bool|:\s*SecretStr" backend/src/agency/config.py
```

**Document in**: `docs/features/README.md` (env var table)

## Frontend — Pages / Routes

**Location**: `frontend/src/app/**/page.tsx`

```bash
# Find all Next.js page components
rg -l "export default" frontend/src/app/ --glob "page.tsx"
```

**Document in**: `docs/features/frontend-pages.md`
**Format**: Route path → page purpose

## Frontend — Components

**Location**: `frontend/src/components/**/*.tsx`

```bash
# Find exported component names
rg "export (default |const |function )\w+" frontend/src/components/ --glob "*.tsx"
```

**Document in**: `docs/features/frontend-components.md`

## Frontend — Hooks

**Location**: `frontend/src/hooks/*.ts`

```bash
rg "export function use\w+" frontend/src/hooks/
```

**Document in**: `docs/features/frontend-components.md` (hooks section)

## Frontend — API Client

**Location**: `frontend/src/lib/api.ts`

```bash
rg "export (async )?function" frontend/src/lib/api.ts
```

**Document in**: `docs/features/frontend-pages.md` (API integration section)

## Alembic Migrations

**Location**: `backend/alembic/versions/*.py`

```bash
# Find migration descriptions
rg "\"\"\".*\"\"\"" backend/alembic/versions/ --glob "*.py"
```

**Document in**: `docs/features/database-schema.md` (migration history section)
