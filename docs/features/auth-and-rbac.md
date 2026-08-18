# Authentication & RBAC
<!-- verified: 260817 -->

## Auth Flow
**Status**: [LIVE]
**File**: `backend/src/agency/dependencies.py`

### Primary: Clerk JWT (RS256)

1. `get_current_user` extracts Bearer token from `Authorization` header
2. If `CLERK_JWKS_URL` and `CLERK_SECRET_KEY` are configured:
   - Fetch JWKS from Clerk (cached ~1 hour)
   - Decode JWT with RS256 using matching `kid`
   - Call Clerk Backend API `GET /v1/users/{sub}` for user details (cached ~5 min)
3. **Auto-provision** if user not in local DB:
   - Create `Organization` named `"{full_name}'s Org"`
   - Create `User` with `password_hash="clerk-managed"`, role `admin`
   - Create `Subscription` with `plan_tier="free"` and limits from `PLAN_CONFIG["free"]` (1 client, 30 posts/mo)
4. Return dict: `{sub, email, role, org_id}`

### Fallback: Legacy JWT (HS256)

If Clerk verification fails or is not configured:
- Decode with `JWT_SECRET` / `HS256`
- Payload must contain: `sub`, `email`, `role`, `org_id`, `exp`
- Issued by `/auth/login` and `/auth/signup` endpoints

### SSE Stream Auth

`GET /campaigns/{id}/stream` uses `?token=` query param (EventSource limitation). Same Clerk-then-legacy verification order. Additionally verifies campaign belongs to user's org.

### Frontend Auth

- **Clerk Provider** wraps the app (`ClerkProvider` in root layout)
- **ClerkTokenSync** component registers `getToken()` with the API client
- **Middleware** (`frontend/middleware.ts`): `clerkMiddleware` protects all routes except `/`, `/sign-in`, `/sign-up`, `/api/webhooks`

## Org Context (Multi-tenancy)

**File**: `backend/src/agency/dependencies.py`, `backend/src/agency/middleware/tenant.py`

- `TenantMiddleware` decodes legacy HS256 JWTs and sets `request.state.org_id`
- `get_org_id` dependency: uses `request.state.org_id` OR falls back to `user["org_id"]` from `get_current_user` (needed for Clerk JWTs which bypass TenantMiddleware)
- All data queries are scoped by `org_id`

### Middleware Stack

Registered in `main.py`. Added first = innermost, so `TenantMiddleware` has already resolved `request.state.org_id` by the time outcomes are recorded.

| Middleware | File | Role |
|------------|------|------|
| `TenantMiddleware` | `middleware/tenant.py` | Decodes `org_id` into `request.state` |
| `ApiKeyAuthMiddleware` | `middleware/api_key_auth.py` | Handles the `X-API-Key` path for `routers/public_api.py` |
| `RequestMetricsMiddleware` | `middleware/request_metrics.py` | In-memory request counters; persists 4xx/5xx only |
| `CORSMiddleware` | — | `CORS_ORIGINS` accepts a JSON array string **or** a comma-separated string |

> ⚠️ **There is no row-level security in the database.** Tenant isolation is enforced entirely in application code, so **every org-scoped query must filter on `org_id`**. A missed filter is a silent cross-tenant data leak.

Two rules that follow, both of which shipped code violated before 260817:

1. **Any id arriving from the client — path param, body field, query string — must be resolved against `org_id` before it is written to or joined on.** A trusted body `client_id` in `routers/oauth.py` let one tenant attach a connected social account to another tenant's client; `routers/publishing.py` then selected that account because its own lookup was unscoped too. Neither gap did anything on its own; together they let an attacker either permanently 500 a victim's publish path or have the victim's content posted with the attacker's token.
2. **`get_current_user` returns the JWT payload dict** — `{sub, email, role, org_id}` — in *both* the Clerk and local HS256 paths, never an ORM `User`. Use the `get_current_user_id` dependency for the caller's id. `user.id` raises `AttributeError` and surfaces as a 500; `routers/comments.py` and `routers/notifications.py` were entirely non-functional for this reason until 260817.

**Tests:** `backend/tests/test_tenancy.py` (clients, campaigns, content) and `backend/tests/test_tenancy_routers.py` (oauth, publishing, comments, notifications, reports, portal). Both run against a real SQLite database so the `WHERE org_id = ...` clauses actually execute. Every test in `test_tenancy_routers.py` has been verified to **fail** when its own filter is deleted — preserve that property when adding cases, because a tenancy test that cannot fail is worse than none.

## Roles

| Role | Permissions |
|------|------------|
| `admin` | Full access: CRUD clients, campaigns, content; team management; billing |
| `member` | Create/edit clients, campaigns, content; no team/billing management |
| `viewer` | Read-only access to all resources |

**Enforcement**: `require_role(*allowed_roles)` dependency factory in `dependencies.py`

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `CLERK_SECRET_KEY` | Clerk Backend API key |
| `CLERK_JWKS_URL` | Clerk JWKS endpoint |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | Clerk frontend key |
| `JWT_SECRET` | Legacy JWT signing key |
| `JWT_ALGORITHM` | `HS256` |
| `JWT_EXPIRE_MINUTES` | Default 60 |

## E2E Test Auth

Uses Clerk Backend API sign-in tokens to bypass instance-level MFA:
1. `createSignInToken()` — Backend API `POST /v1/sign_in_tokens` for test user
2. `page.evaluate()` — `Clerk.client.signIn.create({ strategy: "ticket", ticket })` + `setActive`
3. Env vars: `E2E_CLERK_USER_EMAIL`, `E2E_CLERK_USER_PASSWORD`, `CLERK_SECRET_KEY`
