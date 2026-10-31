-- 261031 — white_label: an uploaded agency logo, stored as bytes.
--
-- Forward-only and additive; safe to re-run. db/init.sql already carries this
-- for fresh databases. Run by hand against Neon BEFORE deploying the backend
-- that ships Settings › Branding: SQLAlchemy names every mapped column in its
-- SELECT, so without these two columns every white_label read fails — the
-- client review page and the campaign pack included, not just the upload.
--
-- Bytes in the row rather than a media_storage key, on purpose: the campaign
-- pack is one self-contained HTML file a client opens anywhere, so the logo
-- travels inside it as a data: URI; the review page is public, and the local
-- media driver's /api/v1/media route is authenticated. One logo per org, capped
-- at 512 KB (services/white_label.py::LOGO_MAX_BYTES). logo_url stays for an
-- externally hosted image and is used only when nothing has been uploaded.

ALTER TABLE white_label ADD COLUMN IF NOT EXISTS logo_data BYTEA;
ALTER TABLE white_label ADD COLUMN IF NOT EXISTS logo_mime VARCHAR(100);

-- primary_color used to default to the old dashboard's indigo, so a row created
-- by the settings screen carried a colour nobody chose. NULL now means "the
-- pack's own accent". Existing rows keep their value.
ALTER TABLE white_label ALTER COLUMN primary_color DROP DEFAULT;

-- Verify:
-- SELECT org_id, logo_mime, octet_length(logo_data) AS logo_bytes FROM white_label;
