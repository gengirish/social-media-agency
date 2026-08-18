-- 260818 — bring an already-provisioned database up to db/init.sql.
--
-- WHY THIS EXISTS
-- db/init.sql runs only when a database is created empty (the docker-compose
-- entrypoint, a fresh Neon branch). Every table and column added to it after
-- provisioning has therefore never reached production. As of 260818 the live
-- Neon branch was missing FOUR tables and TWO columns that models/tables.py
-- declares, which is why the portal and the notifications routes returned 500
-- rather than data.
--
-- Two of these were also missing from init.sql itself, so a fresh database
-- would have been wrong too: `notification` was never declared there, and
-- `white_label` never gained portal_enabled / email_from_name. Both are fixed
-- in init.sql as of this commit; this script covers databases that already
-- exist.
--
-- Forward-only and additive: no drops, no data rewrites. Safe to re-run.
-- Apply with the connection string for the target database, e.g. from inside
-- the Fly machine which already holds NEON_DATABASE_URL.

-- ---------------------------------------------------------------------------
-- 1. white_label — gates the client portal.
-- Without portal_enabled every /api/v1/portal/{org_slug} request raises
-- UndefinedColumn before it can reach its 403.
-- ---------------------------------------------------------------------------
ALTER TABLE white_label ADD COLUMN IF NOT EXISTS portal_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE white_label ADD COLUMN IF NOT EXISTS email_from_name VARCHAR(255);

-- ---------------------------------------------------------------------------
-- 2. notification — declared in models/tables.py, never in init.sql.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS notification (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES organization(id) ON DELETE CASCADE,
    type VARCHAR(50) NOT NULL,
    title VARCHAR(500) NOT NULL,
    body TEXT DEFAULT '',
    data JSONB DEFAULT '{}',
    read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notification_user_created
    ON notification(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notification_user_unread
    ON notification(user_id) WHERE read = FALSE;
CREATE INDEX IF NOT EXISTS idx_notification_org ON notification(org_id);

-- ---------------------------------------------------------------------------
-- 3. webhook + webhook_delivery — in init.sql since T1.3, never provisioned.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS webhook (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL REFERENCES organization(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    events TEXT[] DEFAULT '{}',
    secret VARCHAR(128) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS webhook_delivery (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    webhook_id UUID NOT NULL REFERENCES webhook(id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES organization(id) ON DELETE CASCADE,
    event_type VARCHAR(100) NOT NULL,
    attempt INTEGER NOT NULL DEFAULT 1,
    status VARCHAR(20) NOT NULL DEFAULT 'failed',
    response_code INTEGER,
    error TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_webhook_org ON webhook(org_id);
CREATE INDEX IF NOT EXISTS idx_webhook_org_active ON webhook(org_id, is_active);
CREATE INDEX IF NOT EXISTS idx_webhook_delivery_webhook ON webhook_delivery(webhook_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_webhook_delivery_org ON webhook_delivery(org_id, created_at DESC);

-- ---------------------------------------------------------------------------
-- 4. knowledge_embedding — guarded exactly as in init.sql.
-- pgvector must be enabled per Neon database. If it is not, this block is a
-- no-op and knowledge_base.py keeps reporting retrieval_mode: "keyword".
-- Re-run this file after enabling the extension to pick the table up.
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS vector;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'pgvector unavailable (%) - knowledge_embedding skipped; RAG runs in keyword mode', SQLERRM;
END
$$;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        CREATE TABLE IF NOT EXISTS knowledge_embedding (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            document_id VARCHAR(64) NOT NULL,
            source_path TEXT NOT NULL,
            title VARCHAR(500) NOT NULL DEFAULT '',
            category VARCHAR(100) NOT NULL DEFAULT 'general',
            chunk_index INTEGER NOT NULL DEFAULT 0,
            chunk_text TEXT NOT NULL,
            embedding_provider VARCHAR(50) NOT NULL,
            embedding_model VARCHAR(100) NOT NULL,
            embedding_dim INTEGER NOT NULL,
            embedding vector(1536) NOT NULL,
            metadata JSONB DEFAULT '{}',
            created_at TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT uq_knowledge_embedding_chunk UNIQUE (embedding_model, document_id, chunk_index)
        );
        CREATE INDEX IF NOT EXISTS idx_knowledge_embedding_model
            ON knowledge_embedding(embedding_model);
        CREATE INDEX IF NOT EXISTS idx_knowledge_embedding_document
            ON knowledge_embedding(document_id);
        CREATE INDEX IF NOT EXISTS idx_knowledge_embedding_cosine
            ON knowledge_embedding USING hnsw (embedding vector_cosine_ops);
    ELSE
        RAISE NOTICE 'pgvector not enabled - knowledge_embedding skipped';
    END IF;
END
$$;

-- Verify: expect zero rows from each.
-- SELECT 'missing col' AS problem, 'white_label.' || c AS detail
--   FROM unnest(ARRAY['portal_enabled','email_from_name']) c
--  WHERE NOT EXISTS (SELECT 1 FROM information_schema.columns
--                     WHERE table_name='white_label' AND column_name=c);
-- SELECT 'missing table' AS problem, t AS detail
--   FROM unnest(ARRAY['notification','webhook','webhook_delivery']) t
--  WHERE NOT EXISTS (SELECT 1 FROM information_schema.tables
--                     WHERE table_schema='public' AND table_name=t);
