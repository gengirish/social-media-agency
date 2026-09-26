-- CF-14 — align seeded template categories with the filter taxonomy.
--
-- The Templates filter tabs offered launch / social / awareness /
-- thought-leadership / seasonal / events, but two seeded rows were categorised
-- 'recurring' and 'b2b'. Those two were unreachable from any tab, and the
-- "Social" and "Thought Leadership" tabs returned nothing at all.
--
-- The taxonomy now lives in one place per side — `TEMPLATE_CATEGORIES` in
-- frontend/src/lib/api.ts and db/seed.sql — and this brings already-seeded
-- databases into line with it.
--
-- seed.sql only runs on a fresh database, so this must be applied by hand to any
-- already-provisioned environment (Neon prod, a local volume that was not reset).
-- Forward-only and idempotent: re-running it changes nothing.
--
-- Scoped to the shared public templates (org_id IS NULL). An org that created
-- its own template with either word as a category chose it, so it is left alone.

UPDATE campaign_template
SET category = 'social'
WHERE org_id IS NULL AND category = 'recurring';

UPDATE campaign_template
SET category = 'thought-leadership'
WHERE org_id IS NULL AND category = 'b2b';
