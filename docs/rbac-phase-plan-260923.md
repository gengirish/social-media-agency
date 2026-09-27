# RBAC + account-type (B2C/B2B) — phased parallel plan

Created 260923. Revised 260924 after a pass over the code (see §5 — four gaps that would
have broken the run). Branch off `main` as `feat/rbac-account-type`.

Handover document for parallel Claude subagents. Every agent reads **§1 Locked decisions**
and **§2 Ground rules** before touching anything. The decisions are settled — an agent that
disagrees writes it in its final report and implements the decision anyway.

---

## 1. Locked decisions

**One product, one login.** B2C (solo creator) and B2B (agency) are the same application.
The split is a column on the org, not a second auth surface. Splitting sign-in would break
OAuth: `routers/oauth.py::_first_cors_origin` derives redirect URIs from the first
`CORS_ORIGINS` entry, so a second auth origin silently breaks every callback.

**Two independent axes:**

| Axis | Column | Decides |
|---|---|---|
| Account shape | `organization.account_type` — `'personal'` \| `'business'` | which features exist |
| Seat permission | `users.role` | what this person may do |

**Role vocabulary** collapses to four: `owner`, `admin`, `member`, `viewer`. The legacy
strings map `manager` → `admin`, `content_creator` → `member`.

**Capability matrix** (the single source of truth — `agency/permissions.py`):

| | read | campaign.run | content.approve | publish.write | content.override | oauth.connect | team.manage | billing.manage |
|---|---|---|---|---|---|---|---|---|
| owner  | Y | Y | Y | Y | Y | Y | Y | Y |
| admin  | Y | Y | Y | Y | Y | Y | Y | - |
| member | Y | Y | Y | - | - | - | - | - |
| viewer | Y | - | - | - | - | - | - | - |

Rationale for the `member` row: approve is a human saying the copy is fine (product rule 2
wants a human, and a member is one); publish posts to a live client account and override
bypasses moderation, so both stay owner/admin.

**`account_type` subtracts nothing. Capabilities depend on role alone.** (Revised 260924 —
it originally subtracted `team.manage`, which deadlocked the model: a new org starts
`personal`, `account_type` only flips on the first successful invite, and the invite route is
gated on `team.manage`, so a personal org could never invite and could never become business.
**Inviting a teammate *is* the upgrade, not something the upgrade unlocks.**) `PERSONAL_DENIED`
stays in the code as an empty set so a genuine personal-only restriction has somewhere to
live; `test_account_type_does_not_change_capabilities` stops anyone refilling it by accident.

`account_type` therefore drives exactly two things: **UI affordances** (the nav hides Team for
a solo account) and the **one-way flip**. White-label and the portal need no capability either
— they are gated by `WhiteLabel.portal_enabled`, and a personal org has no `WhiteLabel` row.

**A personal account has exactly one client, auto-created and hidden.** `Campaign.client_id`
is `nullable=False` (`tables.py:205`); making it nullable would touch every join and every
tenancy test. Personal signup creates one `Client` from the user's name; the UI hides the
picker. Flipping to business keeps that client and reveals the picker — no migration.

**`account_type` flips automatically.** Every new org defaults to `'personal'`. It becomes
`'business'` on the first successful team invite or the first growth/agency-tier purchase.
One-way. No question at sign-up.

**Clerk stays identity-only.** Do not adopt Clerk Organizations. There is no RLS in this
database and every scoped query joins on `organization.id`; moving membership into an
external system would put the tenant filter behind a network call. Clerk authenticates,
we authorize.

**Role is read from the database inside the gate, never from the JWT payload, and a missing
user row fails closed.** A demotion must take effect before the token expires, and a deleted
user's unexpired token must not keep its privileges. `get_current_user` returns the payload
dict in both auth modes — `user.get("role")` there is stale by design. This decision is what
forces the test-harness work in Phase 1C; do not soften it to "fall back to the token claim"
to save that work.

**Gates live in routers only, never in services.** `services/scheduler.py::_publish_piece`
publishes on a timer and the agent pipeline writes content — both run with no user in scope.
A capability check inside `services/publishing.py` or `services/content_approval.py` would
break the scheduler at 3am. The service layer stays user-agnostic; the router is the gate.

---

## 2. Ground rules for every agent

1. **Stay inside your `owns` list.** Files outside it are read-only for you. If you believe
   you must edit one, stop and report it instead — another agent owns it right now.
2. **Schema changes are three edits, always:** `db/init.sql`, `backend/src/agency/models/tables.py`,
   and a dated forward-only script in `db/migrations/`. `init.sql` runs only on a fresh
   database, so without the migration the change is invisible on Neon. Nothing applies
   migrations automatically — say so in your report.
3. **Before reporting done:** `ruff check src/ tests/`, `mypy src/agency/ --ignore-missing-imports`,
   `pytest tests/ -v --tb=short` for backend; `npm run lint` and `npm run build` for frontend.
   A clean compile has missed runtime crashes here before. Run the tests.
4. **Every gate test must fail when its gate is deleted.** Verify this by actually deleting
   the line, running the test, and restoring it. `backend/tests/test_tenancy_routers.py` and
   `test_approval_gate.py` already hold this property — match it.
5. **No new role strings.** Import from `agency.permissions`. If you need a capability that
   is not in the matrix, report it; do not invent one.
6. **Phase 2 agents add new test files only.** `backend/tests/conftest.py` belongs to Phase 1C
   and is read-only for everyone else — five agents editing the shared fixture file is the
   one collision this plan cannot absorb.
7. **Do not touch** `.claude/` or `.cursor/` (mirrored trees), `docs/features/` (Phase 4 owns
   it), or any file another phase lists as `owns`.
8. Report format: what changed, what you ran, what passed, what you could not do and why.

---

## 3. Phases

Phases are sequential. Agents **within** a phase run in parallel and share no files.

```
Phase 0  (1 agent, serial)    foundation: permissions.py + schema + migration
   |
Phase 1  (3 agents, parallel) provisioning+/me | vocabulary | test harness
   |
Phase 2  (5 agents, parallel) the seven gates, one router set each
   |
Phase 3  (2 agents, parallel) frontend nav/UI | personal-account onboarding UI
   |
Phase 4  (1 agent, serial)    owner backfill + docs
```

Phase 2 is the one that closes a real hole: today any authenticated user in an org can
connect a social account and publish to it. Phase 1C is the one that, if skipped, turns
Phase 2 into 48 red test files.

---

### Phase 0 — Foundation (1 agent, must finish before anything else)

**Owns:** `backend/src/agency/permissions.py` (new), `backend/src/agency/models/tables.py`,
`db/init.sql`, `db/migrations/260923_rbac_account_type.sql` (new),
`backend/tests/test_permissions.py` (new)

**Task**

1. Create `agency/permissions.py`:
   - `Role` and `Capability` as `Literal` / `StrEnum` — the four roles and eight capabilities above.
   - `CAPS: dict[Role, frozenset[Capability]]` exactly as the matrix.
   - `PERSONAL_DENIED: frozenset[Capability]` = **empty**. See §1 — filling it deadlocks the
     account model. White-label and the portal are NOT capabilities either: they are gated by
     `WhiteLabel.portal_enabled`, and a personal org has no `WhiteLabel` row.
   - `LEGACY_ROLE_MAP = {"manager": "admin", "content_creator": "member"}`.
   - `def capabilities_for(role: str, account_type: str) -> frozenset[Capability]`.
   - `def require_cap(cap: Capability)` — a FastAPI dependency that resolves the caller via
     `get_current_user_id` + `get_org_id`, loads the `User` row (matching **both** `id` and
     `org_id`) and the `Organization.account_type`, and raises
     `403 {"code": "insufficient_permissions", "required": cap}` on a miss. **No user row, or
     a row in another org, or `is_active=False` → 403.** Cache the resolved capability set on
     `request.state` for the request's lifetime — it runs once per gated route, never in a
     module-level dict (that would survive a role change).
   - Import direction is `permissions` → `dependencies`, never the reverse.
2. Add `Organization.account_type` (`String(20)`, not null, default `'personal'`) to `tables.py`
   and `init.sql`.
3. Migration `260923_rbac_account_type.sql`, forward-only and idempotent:
   - `ALTER TABLE organization ADD COLUMN IF NOT EXISTS account_type VARCHAR(20) NOT NULL DEFAULT 'personal';`
   - `UPDATE organization SET account_type = 'business';` — every org that exists today signed
     up under the old assumptions.
   - `UPDATE users SET role = 'admin' WHERE role = 'manager';`
   - `UPDATE users SET role = 'member' WHERE role = 'content_creator';`
   - `UPDATE users SET role = 'viewer' WHERE role NOT IN ('owner','admin','member','viewer');`
   - **Then** the CHECK constraints on `users.role` and `organization.account_type`. Constraints
     last, after the data is clean, or the migration fails on live rows.
   - Add the same CHECK constraints to `init.sql`.
4. `test_permissions.py`: the matrix matches what the code says; `capabilities_for` subtracts
   correctly for `personal`; an unknown role and a missing row both yield the empty set (fail
   closed); and the `CAPS` keys match the allowed values parsed out of the CHECK constraint in
   `init.sql` — so the two cannot drift.

**Acceptance:** no call sites yet, no behaviour change, full suite green.

---

### Phase 1 — Provisioning, vocabulary, test harness (3 agents, parallel)

#### 1A — Both provisioning paths, and `GET /auth/me`

**Owns:** `backend/src/agency/dependencies.py`, `backend/src/agency/routers/auth.py`,
`backend/tests/test_provisioning_roles.py` (new)

**There are two provisioning paths, not one.** `_resolve_clerk_user` in `dependencies.py`
(Clerk/production) and `POST /auth/signup` in `routers/auth.py:47` (local HS256). Both create
`Organization` + `User` + free `Subscription`, and both hardcode `role="admin"`. Fix both, or
the two modes disagree about who owns an org.

**Task**
- New org's first user → `role="owner"`, org → `account_type="personal"`, in **both** paths.
- Both paths also create one `Client` for the org, `brand_name` from the user's name or
  `org_name`, so `Campaign.client_id` (not null) is always satisfiable.
- An existing user row (invited via `team.invite_team_member`) keeps its role — the Clerk
  resolver must match on email before provisioning. Verify it does; add a test either way.
- The `DEMO_ORG_ID` path keeps `role="admin"`, not owner — those users join an existing org.
- `_create_token` carries the role claim; make sure it carries the new vocabulary. The claim
  stays informational — `require_cap` reads the database.
- Add `GET /api/v1/auth/me` returning `{user_id, email, role, org_id, account_type, capabilities}`,
  computed with `capabilities_for`. **Phase 3 cannot start without this** — there is no `/me`
  today (`routers/auth.py` has only `/login` and `/signup`; the `/me` in `public_api.py` is the
  API-key surface and is unrelated).

**Acceptance:** tests cover new org → owner + personal + one client, for Clerk *and* signup;
invited user keeps role; demo-allowlist user gets admin; `/auth/me` returns the right set for
each role and both account types.

#### 1B — Vocabulary cleanup

**Owns:** `backend/src/agency/services/team.py`, `db/seed.sql`,
`backend/tests/test_team_roles.py` (new)

**Task**
- Delete `ROLE_PERMISSIONS` from `services/team.py:11` — it is a second, unrelated role
  vocabulary (`admin`/`manager`/`content_creator`/`viewer`) that only feeds the team-list
  response. Import `CAPS` / `capabilities_for` from `agency.permissions` instead.
- `invite_team_member` validates against the four roles and rejects `owner` — an invite cannot
  mint a second owner.
- `db/seed.sql`: `content_creator` → `member`; add `account_type` to the demo org insert
  (`'business'` — it has a team).

**Acceptance:** one role vocabulary in the codebase.
`grep -rn "content_creator\|\"manager\"" backend/ db/` returns nothing outside the migration's
legacy map.

#### 1C — Test harness (blocks all of Phase 2)

**Owns:** `backend/tests/conftest.py`

**Why this exists.** `auth_header_for` (conftest, ~line 148) mints a token with a **random
`sub` and no `User` row in the database**. 48 test files and 61 call sites rely on it. A
`require_cap` that fails closed on a missing row will 403 every one of them. This is not a
Phase 2 agent's problem to discover five times in parallel.

**Task**
- Add `async def auth_for(session_factory, org_id, role="owner", *, account_type=None) -> dict[str, str]`
  — persists a real `User` row (reuse `create_user_row`) and an org with the right
  `account_type`, then mints a matching HS256 token whose `sub` is that user's id.
- Keep the sync `auth_header_for` for tests that never touch a gated route, but make its
  default role `owner` and document in its docstring that it does **not** create a row and so
  cannot pass a capability gate.
- Give `create_org` an `account_type` parameter (default `'business'`, matching what the
  existing suites assume about team/client behaviour).
- Run the full suite and convert exactly the tests that now fail — no opportunistic rewrites.
  Expect the campaigns, publishing, content, team and billing suites; there should be no
  failures outside the routes Phase 2 gates.
- Do not weaken a gate to make a test pass. If a test cannot be made to pass without that,
  report it.

**Acceptance:** full suite green with Phase 2's gates *not yet added* and green again with a
locally-stubbed gate, proving the harness itself does not depend on the gate's absence.

---

### Phase 2 — Gates (5 agents, parallel; each owns one router set + one new test file)

Every agent: add `Depends(require_cap(...))` to the listed routes, add the test file using
`auth_for` from Phase 1C, verify each test fails with the gate removed. `permissions.py` and
`conftest.py` are read-only.

| Agent | Owns (router) | Routes → capability | Owns (test) |
|---|---|---|---|
| 2A | `routers/oauth.py` | `GET /{platform}/authorize`, `POST /{platform}/callback`, `DELETE /{platform}/{account_id}` → `oauth.connect` | `tests/test_gate_oauth.py` |
| 2B | `routers/publishing.py` | `POST /{content_id}/publish` (`publish_now`, line 49), `POST /{content_id}/schedule` (line 148) → `publish.write` | `tests/test_gate_publishing.py` |
| 2C | `routers/content.py` | `POST /{content_id}/approve` (line 466) → `content.approve`; the `?override=true` branch → `content.override`, checked **inside** the handler after the flag is read | `tests/test_gate_content.py` |
| 2D | `routers/team.py` + `routers/billing.py` | `POST /team/invite`, `PATCH /team/{user_id}/role` → `team.manage`; `POST /billing/checkout` → `billing.manage`. `POST /billing/webhook` is Stripe-authenticated — **leave it ungated** | `tests/test_gate_team_billing.py` |
| 2E | `routers/campaigns.py` + `routers/amplify.py` | `POST /campaigns`, `POST /{campaign_id}/rerun` (line 208), `POST /campaigns/autonomous`, `PATCH /{campaign_id}/review` → `campaign.run`; `POST /amplify/preview`, `POST /amplify/{pack_id}/commit` → `campaign.run` | `tests/test_gate_campaigns.py` |

Notes for **2C**: the override branch must 403 for `member` while the plain approve succeeds —
that distinction is the whole point of the row. Do not change moderation behaviour; the existing
`test_approval_gate.py` must stay green untouched.

Notes for **2D** — this agent has the most to do, and also owns `services/team.py` now that
Phase 1B has landed:
- `team.manage` on the role-update route is what currently lets any user in an org promote
  themselves. Also block a user from changing their own role and from assigning `owner`
  (1B deliberately left `update_member_role` permissive at the service layer so an ownership
  transfer stays expressible — the block belongs here, in the router).
- **Implement the `account_type` flip.** No phase owned it before 260924 and it is the hinge
  of the whole B2C→B2B story: a successful `POST /team/invite` sets the org's `account_type`
  to `'business'`, one way, in the same transaction as the invite. If the invite fails, the
  org stays personal. A second invite is a no-op on an already-business org.
- Test the round trip explicitly: a `personal` org's owner invites → invite succeeds → org is
  now `business`. That test is the proof the deadlock described in §1 is actually gone.

Notes for **2E**: these routes spend generation quota, which is why they are gated at all — a
`viewer` must not be able to burn a month's allowance. `GET /{campaign_id}/stream` stays
ungated beyond `read`: it is an `EventSource` with the JWT in the query string.

**Nobody gates `routers/public_api.py`.** It is authenticated by `X-API-Key` through
`ApiKeyAuthMiddleware`, which sets `request.state.api_key_org_id` and no user at all — a
`require_cap` there would fail on a missing `sub` for every caller. Its two routes are
read-only. If API keys ever need scoping, that is a key-level scope, not a user role.

**Acceptance per agent:** every listed route rejects an under-privileged caller with 403 and
accepts a privileged one; each assertion verified to fail when the `Depends` line is deleted.

---

### Phase 3 — Frontend (2 agents, parallel; both depend on `GET /auth/me` from 1A)

#### 3A — Capability-aware navigation

**Owns:** `frontend/src/lib/navigation.ts`, the top-nav component that consumes it,
`frontend/src/lib/api.ts` (the `/auth/me` call and its types only),
`frontend/e2e/navigation.spec.ts`

**Task**
- Add `requires?: Capability` to `NavTab`; mark Team `team.manage` and Billing `billing.manage`.
- Fetch `/api/v1/auth/me` once per session and filter `NAV_GROUPS` in the nav component.
- `resolveNav` stays pure: filter before calling it, not inside.
- E2E: a viewer sees no Team or Billing tab. Keep the existing per-route H1 assertions green
  (`/content` is "Queue").

This is cosmetic. `middleware.ts` stays a public-route list — a client-side check protects
nothing; Phase 2 is the actual gate.

#### 3B — Role-aware actions and personal-account UI

**Owns:** `frontend/src/app/(dashboard)/content/page.tsx`,
`frontend/src/app/(dashboard)/clients/page.tsx`, `frontend/src/components/clients/`

**Task**
- Hide (do not merely disable) approve for callers without `content.approve`, and
  publish/schedule without `publish.write`. A disabled button that 403s on click is worse than
  an absent one.
- **Setup › Accounts: hide connect and disconnect without `oauth.connect`** (added 260924 by
  2A). `GET /oauth/{platform}/authorize` is now owner/admin-only, so the connect button 403s
  for members and viewers. This route is not on 3B's original file list — the affordance lives
  in the Settings page's platforms tab, so 3B's `owns` list extends to whichever component
  renders it.
- Personal accounts: hide the client picker and present Setup › Clients as the single brand
  record. No "add client" affordance until `account_type === 'business'`.
- Never hardcode a hex colour — use the semantic tokens (`canvas`, `panel`, `ink`, `muted`,
  `line`, `accent`), or it will be wrong in one of the two themes.

Coordination: 3B consumes the same `/auth/me` payload 3A wires up. If 3A has not landed the
fetch yet, read it directly rather than editing 3A's files.

---

### Phase 4 — Backfill and docs (1 agent, after everything)

**Owns:** `db/migrations/260923_owner_backfill.sql` (new), `docs/features/*`,
`docs/rbac-phase-plan-260923.md` (this file — mark phases done)

**Task**
1. **Owner backfill.** Every existing user is `admin` (both provisioning paths hardcoded it),
   so after Phase 1A no existing org has an `owner` and nobody can manage billing. Promote the
   earliest-created user per org:
   `UPDATE users SET role='owner' WHERE id IN (SELECT DISTINCT ON (org_id) id FROM users ORDER BY org_id, created_at);`
   Guard it so it only fires for orgs that have no owner.
2. Refresh `docs/features/` via the `feature-docs` skill — auth/RBAC, API endpoints (`/auth/me`
   and the new 403 code), database schema, changelog.
3. State plainly in the report that **both migrations must be run by hand on Neon**, in which
   order, and that `CORS_ORIGINS` is untouched by this work.

---

## 4. Known hazards

- **`require_cap` adds a DB read per gated request.** Cache on `request.state`; never globally.
- **The invite flow still mails a plaintext temporary password** (`routers/team.py:49`, TODO in
  place). Once roles are enforced, that email is a privilege grant in cleartext. Out of scope
  here; do not let a Phase 2 agent quietly redesign it. Track it separately.
- **Nothing runs migrations automatically.** Two hand-run scripts come out of this plan.
- **Portal auth is untouched.** `routers/portal.py` stays unauthenticated and slug-based. An
  authenticated `client` role scoped to one `client_id` is a separate project — do not let it in
  through this door.
- **The background scheduler must keep publishing.** If `pytest tests/test_scheduler_wake.py`
  goes red in Phase 2, a gate leaked into the service layer. Move it back to the router.

---

## 5. What the 260924 revision changed

Four gaps found by reading the code rather than the plan:

1. **`POST /auth/signup` is a second provisioning path** (`routers/auth.py:47`), also hardcoding
   `role="admin"`, and the original plan had no owner for it and nobody owning the file. Folded
   into 1A.
2. **There is no `/me` endpoint.** The original Phase 3 said "add capabilities to whatever the
   session endpoint returns"; `routers/auth.py` exposes only `/login` and `/signup`. Building it
   is now an explicit 1A task and a stated Phase 3 dependency.
3. **The test harness would have failed every gated test.** `auth_header_for` mints a token with
   a random `sub` and no `User` row — 61 call sites across 48 files. A fail-closed `require_cap`
   403s all of them. New agent 1C owns the fix, before Phase 2, so five parallel agents do not
   each discover it and each edit `conftest.py`.
4. **Gate placement was unstated, and the obvious placement breaks the scheduler.**
   `services/scheduler.py::_publish_piece` publishes with no user in scope. Gates are now
   explicitly router-only, with `public_api.py` (X-API-Key, no user) called out as never gated.

---

## 6. Found during implementation (260924)

**Phase 0 (foundation) — done.** `permissions.py`, `Organization.account_type`, the migration
with CHECK constraints ordered last, 35 tests. No call sites; no behaviour change.

**Phase 1 (provisioning / vocabulary / harness) — done.** Both provisioning paths now mint an
`owner` on a `personal` org with one auto-created `Client`; `GET /auth/me` exists; the second
role vocabulary is gone; `auth_for()` persists real user rows so gated tests can pass.

Two things the phases surfaced that the plan had wrong:

1. **`PERSONAL_DENIED = {team.manage}` deadlocked the account model.** Caught by 1A. A new org
   starts `personal`; `account_type` only flips on a successful invite; the invite route is
   gated on `team.manage`. So no personal org could ever invite, and none could ever become
   business. Fixed by emptying the set — see §1. Three test files asserted the old subtraction
   and now assert its absence, with the reason written into each so nobody "fixes" it back.
2. **Nobody owned the `account_type` flip.** §1 said it flips on the first invite; no phase
   implemented it. Assigned to 2D, which also inherits `services/team.py` from 1B.

Still open, neither blocking:

- `users.is_active` is nullable, and the gate denies on NULL. A row written by raw SQL without
  that column is a silent lockout. Candidate for `NOT NULL DEFAULT TRUE` in Phase 4.
- `ruff` and `mypy` are both red at HEAD (1 and ~418 errors, the latter measured mid-edit).
  CLAUDE.md requires both clean before presenting a change. Each agent has verified it adds
  none of its own, but the baseline itself needs a decision.
- The fresh `docker compose` boot fix (seed.sql) is verified statically only — the Docker
  daemon was not running. Worth one real boot against a deleted `pgdata` volume.
- `GET /team`'s `permissions` field changed shape (verbs → capability names). Checked: no
  frontend component renders it, only a type in `lib/api.ts`. No action needed.
