-- 260923 — Amplify can repurpose a saved Create-screen asset.
--
-- repurpose_pack.source_asset_id points at the creative_asset a pack was made
-- from (blog post, comparison page, niche scan, video script, launch kit).
-- Forward-only and additive; safe to re-run. Requires 260923_creative_asset.sql
-- first. db/init.sql already carries this for fresh databases. Run by hand on
-- Neon BEFORE deploying the backend that reads it, or /api/v1/amplify/* fails
-- with UndefinedColumn.

ALTER TABLE repurpose_pack
    ADD COLUMN IF NOT EXISTS source_asset_id UUID REFERENCES creative_asset(id) ON DELETE SET NULL;

-- Verify:
-- SELECT count(*) FROM repurpose_pack WHERE source_asset_id IS NOT NULL;
