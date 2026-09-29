-- Manual channels — a page the operator posts to themselves, with no OAuth.
--
-- A manual channel is a ``platform_account`` row with ``status = 'manual'`` and
-- no tokens (``access_token_enc`` is already nullable, so nothing to relax).
-- Every token-requiring call site filters ``status = 'connected'`` and therefore
-- excludes these rows by default; only the two display paths
-- (``routers/setup.py::client_accounts`` and ``routers/clients.py`` overview
-- counts) were widened. See docs/manual-publish-plan-260929.md §1.
--
-- ``profile_url`` is the page's public address: the link the UI renders (target
-- _blank) and the per-channel override for a composer deep link that has rotted.
-- Optional — a channel with no URL is still a valid record.
--
-- init.sql only runs on a fresh database, so this must be applied by hand to any
-- already-provisioned environment (Neon prod, a local volume that was not reset).
-- Forward-only and idempotent.

ALTER TABLE platform_account ADD COLUMN IF NOT EXISTS profile_url TEXT;
