-- 260923 — inbox_item_state: triage state (read / handled / replied) for the
-- Inbox screen. Inbox items themselves are fetched live from X and LinkedIn and
-- never stored; this table only records what a human did with one.
--
-- Forward-only and additive; safe to re-run. db/init.sql already carries this
-- for fresh databases. Run by hand against Neon BEFORE deploying the backend
-- that ships routers/inbox.py, or /api/v1/inbox fails with UndefinedTable.

CREATE TABLE IF NOT EXISTS inbox_item_state (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL REFERENCES organization(id) ON DELETE CASCADE,
    client_id UUID NOT NULL REFERENCES client(id) ON DELETE CASCADE,
    item_key VARCHAR(255) NOT NULL,
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    handled BOOLEAN NOT NULL DEFAULT FALSE,
    reply_id VARCHAR(255),
    reply_url TEXT,
    updated_by UUID REFERENCES users(id) ON DELETE SET NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (org_id, client_id, item_key)
);

-- Verify:
-- SELECT count(*) FROM inbox_item_state;
