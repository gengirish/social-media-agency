-- CF-07 — record why a campaign run failed.
--
-- A failed campaign carried no reason anywhere: the list showed "Failed" cards
-- with nothing to act on, and the detail page said nothing either. The pipeline
-- logged the exception and dropped it. This column is where it goes instead:
--
--     {
--       "error":      "<the exception message>",
--       "error_type": "<exception class name>",
--       "agents":     ["create_content"],   -- who it could have been, [] if unknown
--       "after":      "seo_research",       -- last agent that finished, null if none
--       "at":         "2026-09-25T09:14:00+00:00"
--     }
--
-- Empty '{}' for every campaign that has not failed.
--
-- init.sql only runs on a fresh database, so this must be applied by hand to any
-- already-provisioned environment (Neon prod, a local volume that was not reset).
-- Forward-only and idempotent.

ALTER TABLE campaign ADD COLUMN IF NOT EXISTS failure JSONB DEFAULT '{}';

-- Existing failed campaigns have no recoverable reason — the exception was only
-- ever logged. They are left with '{}', which the UI renders as "no reason was
-- recorded" rather than inventing one.
