# Authentication & RBAC
<!-- verified: 260324 -->

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
   - Create `Subscription` with `plan_tier="free"`, 2 clients, 30 posts
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
