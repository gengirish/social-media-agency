-- 260921 — Amplify (repurposing engine): pack history table + generation quota.
--
-- Forward-only and additive; safe to re-run. db/init.sql already carries all of
-- this for fresh databases — this script is for already-provisioned ones (Neon
-- prod, a local volume that was not reset). Nothing applies it automatically:
-- run it by hand against the target database BEFORE deploying the backend that
-- ships routers/amplify.py, or /api/v1/amplify/* and /billing/subscription will
-- fail with UndefinedColumn / UndefinedTable.

-- ---------------------------------------------------------------------------
-- 1. Generation quota on subscription. 1 Amplify pack = 1 generation.
-- ---------------------------------------------------------------------------
ALTER TABLE subscription ADD COLUMN IF NOT EXISTS generations_used INTEGER NOT NULL DEFAULT 0;
ALTER TABLE subscription ADD COLUMN IF NOT EXISTS generations_limit INTEGER;

-- Backfill limits from the tier. MUST match PLAN_CONFIG in
-- backend/src/agency/services/billing.py. (The app also falls back to
-- PLAN_CONFIG when the column is NULL, so an unknown tier is not locked out.)
UPDATE subscription
SET generations_limit = CASE plan_tier
    WHEN 'free' THEN 10
    WHEN 'starter' THEN 50
    WHEN 'growth' THEN 250
    WHEN 'agency' THEN 9999
    ELSE generations_limit
END
WHERE generations_limit IS NULL;

-- ---------------------------------------------------------------------------
-- 2. repurpose_pack — one row per generated pack.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS repurpose_pack (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL REFERENCES organization(id) ON DELETE CASCADE,
    client_id UUID NOT NULL REFERENCES client(id) ON DELETE CASCADE,
    source_content_id UUID REFERENCES content_piece(id) ON DELETE SET NULL,
    source_text TEXT,
    platforms JSONB NOT NULL DEFAULT '[]',
    atom_count INTEGER NOT NULL DEFAULT 0,
    committed_count INTEGER NOT NULL DEFAULT 0,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_repurpose_pack_org_created
    ON repurpose_pack(org_id, created_at DESC);

-- Verify:
-- SELECT column_name FROM information_schema.columns
--   WHERE table_name = 'subscription' AND column_name LIKE 'generations_%';
-- SELECT count(*) FROM repurpose_pack;
