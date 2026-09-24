-- 260923 — RBAC roles + organization.account_type.
--
-- This repo has no Alembic (schema lives in db/init.sql), and init.sql only runs on a
-- FRESH database. Run this by hand on Neon — nothing applies it automatically.
-- Forward-only and idempotent: safe to run twice.
--
-- Two independent axes come out of this script:
--   organization.account_type  'personal' | 'business'  -> which features exist
--   users.role                 owner|admin|member|viewer -> what a seat may do
--
-- ORDER MATTERS. The CHECK constraints go LAST, after the data-cleaning UPDATEs.
-- Adding them first would fail on the live rows they exist to prevent.

BEGIN;

-- 1. The new column. Defaults to 'personal' so that every org created from here on
--    starts as a solo account and flips to 'business' on its first invite/upgrade.
ALTER TABLE organization
    ADD COLUMN IF NOT EXISTS account_type VARCHAR(20) NOT NULL DEFAULT 'personal';

-- 2. Every org that already exists signed up under the old assumptions: a team, a
--    client list, a portal. They are all businesses. Unconditional on purpose —
--    at the time this runs there is no org that chose 'personal'.
UPDATE organization SET account_type = 'business' WHERE account_type <> 'business';

-- 3. Collapse the legacy role vocabulary onto the four roles.
UPDATE users SET role = 'admin'  WHERE role = 'manager';
UPDATE users SET role = 'member' WHERE role = 'content_creator';

-- 4. Anything still unrecognised becomes the least-privileged role. Fail closed:
--    an unknown role string resolves to no capabilities anyway, and this makes that
--    explicit in the data instead of leaving a row the CHECK would reject.
UPDATE users SET role = 'viewer'
WHERE role NOT IN ('owner', 'admin', 'member', 'viewer');

-- 5. Constraints last, now that the data satisfies them.
ALTER TABLE organization DROP CONSTRAINT IF EXISTS organization_account_type_check;
ALTER TABLE organization
    ADD CONSTRAINT organization_account_type_check
    CHECK (account_type IN ('personal', 'business'));

ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
ALTER TABLE users
    ADD CONSTRAINT users_role_check
    CHECK (role IN ('owner', 'admin', 'member', 'viewer'));

COMMIT;

-- Verify: both expect zero rows.
-- SELECT id, role FROM users WHERE role NOT IN ('owner','admin','member','viewer');
-- SELECT id, account_type FROM organization WHERE account_type NOT IN ('personal','business');
--
-- NOTE: after Phase 1A this leaves every existing org without an `owner` (both
-- provisioning paths hardcoded 'admin'), so nobody can manage billing. That is what
-- db/migrations/260923_owner_backfill.sql fixes — run it after this one.
