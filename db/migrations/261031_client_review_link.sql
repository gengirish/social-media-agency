-- 261031 — client_review_link: per-client review links, replacing the org-slug portal.
--
-- Forward-only and additive; safe to re-run. db/init.sql already carries this
-- for fresh databases. Run by hand against Neon BEFORE deploying the backend
-- that ships routers/review_links.py, or creating a review link fails with
-- UndefinedTable. Nothing else reads the table, so skipping it breaks only
-- review links, not existing routes.
--
-- The old /api/v1/portal/{org_slug} routes are removed in the same release.
-- white_label.portal_enabled stays as a column but nothing reads it any more.

CREATE TABLE IF NOT EXISTS client_review_link (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL REFERENCES organization(id) ON DELETE CASCADE,
    client_id UUID NOT NULL REFERENCES client(id) ON DELETE CASCADE,
    campaign_id UUID REFERENCES campaign(id) ON DELETE CASCADE,
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_client_review_link_org_client
    ON client_review_link(org_id, client_id, created_at DESC);

-- Verify:
-- SELECT count(*) FROM client_review_link;
