-- 260923 — creative_asset: stored output of the Create screens (Content, Email,
-- Launch, Ads), Insights advocacy and Setup strategy lens.
--
-- Forward-only and additive; safe to re-run. db/init.sql already carries this
-- for fresh databases. Run by hand against Neon BEFORE deploying the backend
-- that ships routers/assets.py, or /api/v1/assets/* fails with UndefinedTable.

-- ---------------------------------------------------------------------------
-- creative_asset — long-form output of the Create screens (Content, Email,
-- Launch, Ads, Insights' advocacy, Setup's strategy lens). One row per
-- generation the human chose to keep. ``kind`` is a closed set enforced in
-- services/creative_assets.py::ASSET_KINDS; ``payload`` is the kind's JSON
-- shape. Social posts are NOT stored here — they live in content_piece so the
-- approval gate applies to them.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS creative_asset (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL REFERENCES organization(id) ON DELETE CASCADE,
    client_id UUID NOT NULL REFERENCES client(id) ON DELETE CASCADE,
    kind VARCHAR(40) NOT NULL,
    title VARCHAR(500) NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}',
    source_asset_id UUID REFERENCES creative_asset(id) ON DELETE SET NULL,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_creative_asset_org_client_kind
    ON creative_asset(org_id, client_id, kind, created_at DESC);

-- Verify:
-- SELECT count(*) FROM creative_asset;
