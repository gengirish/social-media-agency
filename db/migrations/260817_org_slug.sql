-- 260817 — add organization.slug for the client portal.
--
-- This repo has no Alembic (schema lives in db/init.sql), so migrations against an
-- already-provisioned database are applied by hand. Run this on the Neon branch before
-- deploying the portal changes; init.sql already carries the column for fresh databases.
--
-- Why: /api/v1/portal/{org_slug} is unauthenticated and previously resolved orgs on
-- `domain` then `name`, neither of which is unique. Two orgs sharing a name made the
-- lookup raise (500 on the whole portal) and a name could shadow another org's slug.

ALTER TABLE organization ADD COLUMN IF NOT EXISTS slug VARCHAR(64);

-- Backfill: lowercase, hyphenated name, de-duplicated by row number. Orgs whose slug
-- cannot be derived keep NULL, which means "no portal" — the fail-closed default.
WITH slugged AS (
    SELECT
        id,
        NULLIF(trim(both '-' from regexp_replace(lower(name), '[^a-z0-9]+', '-', 'g')), '') AS base,
        row_number() OVER (
            PARTITION BY NULLIF(trim(both '-' from regexp_replace(lower(name), '[^a-z0-9]+', '-', 'g')), '')
            ORDER BY created_at, id
        ) AS n
    FROM organization
    WHERE slug IS NULL
)
UPDATE organization o
SET slug = CASE WHEN s.n = 1 THEN left(s.base, 64) ELSE left(s.base, 57) || '-' || s.n END
FROM slugged s
WHERE o.id = s.id AND s.base IS NOT NULL;

ALTER TABLE organization DROP CONSTRAINT IF EXISTS organization_slug_key;
ALTER TABLE organization ADD CONSTRAINT organization_slug_key UNIQUE (slug);

-- Verify: expect zero rows.
-- SELECT slug, count(*) FROM organization WHERE slug IS NOT NULL GROUP BY slug HAVING count(*) > 1;
