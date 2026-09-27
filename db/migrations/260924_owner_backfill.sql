-- 260924 — promote one owner per organization, and close the is_active NULL hole.
--
-- RUN THIS SECOND. `db/migrations/260923_rbac_account_type.sql` must have run first:
-- this script assumes `users.role` already holds only the four canonical roles and
-- that `organization.account_type` exists. Nothing applies either automatically —
-- both are hand-run on Neon (no Alembic in this repo; init.sql is fresh-DB only).
--
-- Forward-only and idempotent: safe to run twice.
--
-- WHY THIS EXISTS. Before the RBAC work both provisioning paths hardcoded
-- role='admin' (`dependencies.py::_resolve_clerk_user` and `routers/auth.py::signup`),
-- so no organization has an 'owner'. `billing.manage` belongs to owner alone, which
-- means that without this script **every existing org loses access to its own
-- billing** the moment the gates ship. Phase 1A fixed new signups; this fixes history.

BEGIN;

-- 1. Exactly one owner per org: the earliest-created member, which for every org
--    created by either provisioning path is the person who signed up.
--
--    Guarded by NOT EXISTS so it only touches orgs that have no owner yet. That is
--    what makes a second run a no-op, and it also means a deliberate ownership
--    transfer done later is never silently reverted by re-running this.
--
--    created_at can tie (same-transaction seed inserts), so id is the tiebreaker —
--    without it DISTINCT ON picks arbitrarily and two runs could disagree.
UPDATE users
SET role = 'owner'
WHERE id IN (
    SELECT DISTINCT ON (u.org_id) u.id
    FROM users u
    WHERE u.is_active IS NOT FALSE
      AND NOT EXISTS (
          SELECT 1 FROM users o
          WHERE o.org_id = u.org_id AND o.role = 'owner'
      )
    ORDER BY u.org_id, u.created_at, u.id
);

-- 2. `users.is_active` is nullable, and the capability gate denies on NULL
--    (`resolve_capabilities` filters `is_active IS TRUE`, which excludes NULL).
--    A row written by raw SQL that omitted the column is therefore a silent
--    lockout: the user authenticates fine and then 403s on everything.
--    Backfill, then make the column honest.
UPDATE users SET is_active = TRUE WHERE is_active IS NULL;

ALTER TABLE users ALTER COLUMN is_active SET DEFAULT TRUE;
ALTER TABLE users ALTER COLUMN is_active SET NOT NULL;

COMMIT;

-- Verify — the first two expect zero rows, the third expects one row per org.
--
-- Orgs with no owner (should be none that have any active user):
--   SELECT o.id, o.name FROM organization o
--   WHERE NOT EXISTS (SELECT 1 FROM users u WHERE u.org_id = o.id AND u.role = 'owner')
--     AND EXISTS (SELECT 1 FROM users u WHERE u.org_id = o.id);
--
-- Orgs with more than one owner (this script never creates one, but a manual
-- promotion might have):
--   SELECT org_id, COUNT(*) FROM users WHERE role = 'owner'
--   GROUP BY org_id HAVING COUNT(*) > 1;
--
-- Any remaining NULL is_active (should be impossible after the ALTER):
--   SELECT id, email FROM users WHERE is_active IS NULL;
