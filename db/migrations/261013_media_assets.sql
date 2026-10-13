-- ---------------------------------------------------------------------------
-- 261013 — generated media (images, short video) attached to a post.
--
-- Plan: docs/media-generation-plan-261009.md
--
-- Forward-only. Run by hand on Neon; nothing applies these automatically.
-- Mirrored into db/init.sql and models/tables.py in the same commit --
-- SQLAlchemy names every mapped column in its SELECT, so a model column
-- without the matching migration breaks EVERY read of that table.
-- ---------------------------------------------------------------------------

-- Media quota is deliberately NOT the text generations counter. One video can
-- cost an order of magnitude more than one LLM call, so a shared counter lets
-- an agency-tier org (generations_limit 9999 at $168) run up fal spend far
-- above its revenue. Weights live in config.py::media_credit_weight.
--
-- A NULL limit falls back to the tier's PLAN_CONFIG value (see
-- services/media_credits.py::media_credits_limit_for), exactly as
-- generations_limit does -- never to "unlimited".
ALTER TABLE subscription
    ADD COLUMN IF NOT EXISTS media_credits_used INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS media_credits_limit INTEGER,
    -- Counted separately from credits and capped per tier even on agency:
    -- 9999 is a sentinel meaning unlimited, and unlimited video generation is
    -- unbounded loss.
    ADD COLUMN IF NOT EXISTS videos_used INTEGER NOT NULL DEFAULT 0;

-- ---------------------------------------------------------------------------
-- media_asset -- one row per generated image or video we kept.
--
-- NOT creative_asset: that table is long-form text in a JSONB payload behind a
-- closed ASSET_KINDS, rendered as prose by the generic /assets CRUD. A binary
-- needs a storage key, mime, dimensions, duration and a moderation verdict,
-- none of which fit payload without those screens showing garbage.
--
-- content_piece.media_urls stays as the publish-facing list of resolved URLs
-- (content_approval.py already depends on it, and the publishers read it).
-- This table is the record; media_urls is the denormalised projection. Both are
-- written in the same transaction.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS media_asset (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL REFERENCES organization(id) ON DELETE CASCADE,
    client_id UUID NOT NULL REFERENCES client(id) ON DELETE CASCADE,
    -- Nullable: an asset generated before it is attached to a post is valid,
    -- and deleting the post should not delete the asset the user paid for.
    content_id UUID REFERENCES content_piece(id) ON DELETE SET NULL,
    kind VARCHAR(20) NOT NULL,
    -- Storage key, not a URL: the public URL is derived from the key by the
    -- active driver, so moving buckets or domains does not rewrite rows.
    storage_key VARCHAR(500) NOT NULL,
    url TEXT NOT NULL DEFAULT '',
    thumb_url TEXT NOT NULL DEFAULT '',
    mime VARCHAR(100) NOT NULL DEFAULT '',
    width INTEGER,
    height INTEGER,
    duration_ms INTEGER,
    bytes INTEGER,
    model VARCHAR(120) NOT NULL DEFAULT '',
    -- The resolved prompt, assembled in code from the creative brief + brand
    -- context. Stored so a regenerate is reproducible and so prompt_hash means
    -- something auditable.
    prompt TEXT NOT NULL DEFAULT '',
    prompt_hash VARCHAR(64) NOT NULL DEFAULT '',
    credits_charged INTEGER NOT NULL DEFAULT 0,
    -- Moderation verdict, written at GENERATION time, not approval time. An
    -- empty object means "not yet screened" and the approve path refuses it --
    -- a row lookup, not a model call, so rule 3 costs no approval latency.
    moderation JSONB NOT NULL DEFAULT '{}',
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_media_asset_org_client
    ON media_asset(org_id, client_id, created_at DESC);

-- The approve path and the post card both load a piece's media by content_id.
CREATE INDEX IF NOT EXISTS idx_media_asset_content
    ON media_asset(content_id)
    WHERE content_id IS NOT NULL;

-- Dedupe: a repeated generate returns the existing asset and charges nothing.
-- Scoped to the org, so one tenant's prompt can never resolve to another's
-- bytes. Partial, because '' is the pre-generation placeholder and would
-- otherwise collide on the second row.
CREATE UNIQUE INDEX IF NOT EXISTS idx_media_asset_dedupe
    ON media_asset(org_id, prompt_hash)
    WHERE prompt_hash <> '';

-- ---------------------------------------------------------------------------
-- media_job -- async provider work, for video.
--
-- Video must NOT use the sync fal.run endpoint the image path uses: it blocks a
-- worker for the whole generation, which is fine at a few seconds and fatal at
-- minutes (starved workers, then Fly's request timeout). queue.fal.run returns
-- a job id and this row tracks it.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS media_job (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL REFERENCES organization(id) ON DELETE CASCADE,
    media_asset_id UUID REFERENCES media_asset(id) ON DELETE CASCADE,
    provider VARCHAR(40) NOT NULL DEFAULT 'fal',
    provider_job_id VARCHAR(200) NOT NULL DEFAULT '',
    status VARCHAR(20) NOT NULL DEFAULT 'queued',
    error TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- The poller sweeps unfinished jobs across every org, like the scheduler does.
CREATE INDEX IF NOT EXISTS idx_media_job_pending
    ON media_job(status, created_at)
    WHERE status IN ('queued', 'running');
