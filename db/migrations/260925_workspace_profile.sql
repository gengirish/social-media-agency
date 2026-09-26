-- 260925 — organization.workspace_profile.
--
-- No Alembic in this repo (schema lives in db/init.sql), and init.sql only runs on a
-- FRESH database. Run this by hand on Neon — nothing applies it automatically.
-- Forward-only and idempotent: safe to run twice.
--
-- What this column is: how a workspace describes itself, chosen by the person on the
-- pricing screen. It reshapes which plans are offered and which is recommended. It is
-- PRESENTATION ONLY — it grants no capability, changes no limit, and is not a tier.
-- `subscription` stays the only source of truth for what an org may actually do.
--
-- Why it is not `organization.account_type`: account_type is a two-value one-way flip
-- ('personal' -> 'business') that drives capabilities in agency/permissions.py. Folding
-- a user-chosen, freely-changeable label into it would let a pricing-page click silently
-- move someone's permissions.
--
-- NULL is meaningful and is the default: never chosen -> the full plan grid is shown.
-- Existing orgs are left NULL rather than guessed at.

BEGIN;

ALTER TABLE organization
    ADD COLUMN IF NOT EXISTS workspace_profile VARCHAR(24);

-- Constraint last, so it can never fail on rows that predate it. NULL passes.
ALTER TABLE organization DROP CONSTRAINT IF EXISTS organization_workspace_profile_check;
ALTER TABLE organization
    ADD CONSTRAINT organization_workspace_profile_check
    CHECK (workspace_profile IS NULL
           OR workspace_profile IN ('product_owner', 'freelancer', 'organization'));

COMMIT;

-- Verify: expects zero rows.
-- SELECT id, workspace_profile FROM organization
-- WHERE workspace_profile IS NOT NULL
--   AND workspace_profile NOT IN ('product_owner','freelancer','organization');
