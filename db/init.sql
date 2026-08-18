CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE SCHEMA IF NOT EXISTS campaignforge;

-- Organizations (tenants)
CREATE TABLE IF NOT EXISTS organization (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    -- Portal identity. UNIQUE is load-bearing: /api/v1/portal/{org_slug} is
    -- unauthenticated, so a non-unique key lets one org shadow another's namespace.
    -- Nullable = no portal for that org (fails closed).
    slug VARCHAR(64) UNIQUE,
    domain VARCHAR(255),
    settings JSONB DEFAULT '{}',
    agentmail_inbox_id VARCHAR(255),
    agentmail_email VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Users
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL REFERENCES organization(id) ON DELETE CASCADE,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'viewer',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Subscriptions
CREATE TABLE IF NOT EXISTS subscription (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL REFERENCES organization(id) ON DELETE CASCADE,
    stripe_customer_id VARCHAR(255),
    stripe_subscription_id VARCHAR(255),
    plan_tier VARCHAR(50) NOT NULL DEFAULT 'free',
    clients_limit INTEGER DEFAULT 2,
    posts_limit INTEGER DEFAULT 30,
    posts_used INTEGER DEFAULT 0,
    current_period_start TIMESTAMPTZ,
    current_period_end TIMESTAMPTZ,
    status VARCHAR(50) DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Clients / Brands
CREATE TABLE IF NOT EXISTS client (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL REFERENCES organization(id) ON DELETE CASCADE,
    brand_name VARCHAR(255) NOT NULL,
    industry VARCHAR(100),
    description TEXT DEFAULT '',
    website_url VARCHAR(500),
    contact_email VARCHAR(255),
    logo_url TEXT,
    settings JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Brand Profiles (enriched brand voice)
CREATE TABLE IF NOT EXISTS brand_profile (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id UUID NOT NULL UNIQUE REFERENCES client(id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES organization(id),
    voice_description TEXT DEFAULT '',
    tone_attributes JSONB DEFAULT '{}',
    vocabulary_include TEXT[] DEFAULT '{}',
    vocabulary_exclude TEXT[] DEFAULT '{}',
    example_posts JSONB DEFAULT '[]',
    style_rules TEXT[] DEFAULT '{}',
    emoji_policy VARCHAR(20) DEFAULT 'moderate',
    competitor_differentiation TEXT DEFAULT '',
    target_audience TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Platform Accounts
CREATE TABLE IF NOT EXISTS platform_account (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id UUID NOT NULL REFERENCES client(id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES organization(id),
    platform VARCHAR(50) NOT NULL,
    account_handle VARCHAR(255) NOT NULL,
    display_name VARCHAR(255),
    access_token_enc TEXT,
    refresh_token_enc TEXT,
    token_expires_at TIMESTAMPTZ,
    followers_count INTEGER DEFAULT 0,
    status VARCHAR(30) DEFAULT 'connected',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Campaigns
CREATE TABLE IF NOT EXISTS campaign (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id UUID NOT NULL REFERENCES client(id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES organization(id),
    name VARCHAR(255) NOT NULL,
    objective TEXT DEFAULT '',
    channels TEXT[] DEFAULT '{}',
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    budget JSONB DEFAULT '{}',
    status VARCHAR(30) DEFAULT 'planning',
    agent_plan JSONB DEFAULT '{}',
    tags JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Agent Runs (every agent call recorded)
CREATE TABLE IF NOT EXISTS agent_run (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    campaign_id UUID NOT NULL REFERENCES campaign(id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES organization(id),
    agent_name VARCHAR(50) NOT NULL,
    input_summary TEXT DEFAULT '',
    output TEXT DEFAULT '',
    tokens_used INTEGER DEFAULT 0,
    model_used VARCHAR(100) DEFAULT '',
    duration_ms INTEGER DEFAULT 0,
    cost_usd NUMERIC(10, 6) DEFAULT 0,
    status VARCHAR(30) DEFAULT 'running',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Workflow State (metadata — checkpoints handled by LangGraph PostgresSaver)
CREATE TABLE IF NOT EXISTS workflow (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    campaign_id UUID NOT NULL UNIQUE REFERENCES campaign(id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES organization(id),
    current_node VARCHAR(50) DEFAULT '',
    status VARCHAR(30) DEFAULT 'running',
    total_duration_ms INTEGER DEFAULT 0,
    total_cost_usd NUMERIC(10, 6) DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

-- Content Pieces
CREATE TABLE IF NOT EXISTS content_piece (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    campaign_id UUID REFERENCES campaign(id) ON DELETE SET NULL,
    client_id UUID NOT NULL REFERENCES client(id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES organization(id),
    agent_run_id UUID REFERENCES agent_run(id) ON DELETE SET NULL,
    content_type VARCHAR(50) DEFAULT 'social_post',
    platform VARCHAR(50) NOT NULL,
    title VARCHAR(500) DEFAULT '',
    body TEXT DEFAULT '',
    hashtags JSONB DEFAULT '[]',
    metadata JSONB DEFAULT '{}',
    media_urls JSONB DEFAULT '[]',
    ai_generated BOOLEAN DEFAULT TRUE,
    status VARCHAR(30) DEFAULT 'draft',
    performance_score FLOAT,
    scheduled_at TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Analytics Snapshots
CREATE TABLE IF NOT EXISTS analytics_snapshot (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    platform_account_id UUID NOT NULL REFERENCES platform_account(id) ON DELETE CASCADE,
    content_id UUID REFERENCES content_piece(id) ON DELETE SET NULL,
    date DATE NOT NULL,
    impressions INTEGER DEFAULT 0,
    reach INTEGER DEFAULT 0,
    engagement INTEGER DEFAULT 0,
    clicks INTEGER DEFAULT 0,
    shares INTEGER DEFAULT 0,
    likes INTEGER DEFAULT 0,
    followers_delta INTEGER DEFAULT 0,
    extra JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_users_org ON users(org_id);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_client_org ON client(org_id);
CREATE INDEX IF NOT EXISTS idx_brand_profile_client ON brand_profile(client_id);
CREATE INDEX IF NOT EXISTS idx_platform_account_client ON platform_account(client_id);
CREATE INDEX IF NOT EXISTS idx_platform_account_org ON platform_account(org_id);
CREATE INDEX IF NOT EXISTS idx_campaign_client ON campaign(client_id);
CREATE INDEX IF NOT EXISTS idx_campaign_org ON campaign(org_id);
CREATE INDEX IF NOT EXISTS idx_campaign_status ON campaign(status);
CREATE INDEX IF NOT EXISTS idx_agent_run_campaign ON agent_run(campaign_id);
CREATE INDEX IF NOT EXISTS idx_agent_run_org ON agent_run(org_id);
CREATE INDEX IF NOT EXISTS idx_workflow_campaign ON workflow(campaign_id);
CREATE INDEX IF NOT EXISTS idx_content_piece_campaign ON content_piece(campaign_id);
CREATE INDEX IF NOT EXISTS idx_content_piece_org ON content_piece(org_id);
CREATE INDEX IF NOT EXISTS idx_content_piece_client ON content_piece(client_id);
CREATE INDEX IF NOT EXISTS idx_content_piece_status ON content_piece(status);
CREATE INDEX IF NOT EXISTS idx_analytics_account ON analytics_snapshot(platform_account_id);
CREATE INDEX IF NOT EXISTS idx_analytics_date ON analytics_snapshot(date);

-- Comments on content pieces
CREATE TABLE IF NOT EXISTS content_comment (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    content_id UUID NOT NULL REFERENCES content_piece(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES organization(id),
    body TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- White-label branding for agency mode
CREATE TABLE IF NOT EXISTS white_label (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL UNIQUE REFERENCES organization(id) ON DELETE CASCADE,
    custom_domain VARCHAR(255),
    logo_url TEXT,
    primary_color VARCHAR(7) DEFAULT '#4f46e5',
    company_name VARCHAR(255),
    support_email VARCHAR(255),
    -- Gates every /api/v1/portal/{org_slug} route. Defaults FALSE so an org that
    -- has branding rows but has not opted in still 403s.
    portal_enabled BOOLEAN DEFAULT FALSE,
    email_from_name VARCHAR(255),
    is_active BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Campaign templates
CREATE TABLE IF NOT EXISTS campaign_template (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID REFERENCES organization(id),
    name VARCHAR(255) NOT NULL,
    description TEXT DEFAULT '',
    category VARCHAR(100) DEFAULT 'general',
    objective_template TEXT DEFAULT '',
    channels TEXT[] DEFAULT '{}',
    content_directives JSONB DEFAULT '{}',
    is_public BOOLEAN DEFAULT FALSE,
    uses_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- API keys for external integrations
CREATE TABLE IF NOT EXISTS api_key (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL REFERENCES organization(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    key_hash VARCHAR(255) NOT NULL,
    key_prefix VARCHAR(10) NOT NULL,
    permissions TEXT[] DEFAULT '{read}',
    is_active BOOLEAN DEFAULT TRUE,
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_content_comment_content ON content_comment(content_id);
CREATE INDEX IF NOT EXISTS idx_content_comment_org ON content_comment(org_id);
CREATE INDEX IF NOT EXISTS idx_white_label_org ON white_label(org_id);
CREATE INDEX IF NOT EXISTS idx_campaign_template_org ON campaign_template(org_id);
CREATE INDEX IF NOT EXISTS idx_campaign_template_public ON campaign_template(is_public);
CREATE INDEX IF NOT EXISTS idx_api_key_org ON api_key(org_id);
CREATE INDEX IF NOT EXISTS idx_api_key_prefix ON api_key(key_prefix);

CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL REFERENCES organization(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(100),
    resource_id VARCHAR(255),
    details JSONB DEFAULT '{}',
    ip_address VARCHAR(45),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_log_org ON audit_log(org_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_org_created ON audit_log(org_id, created_at DESC);

-- Product analytics event stream (beta metrics — see docs/beta-testing-plan.md §7)
CREATE TABLE IF NOT EXISTS product_event (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID REFERENCES organization(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    session_id VARCHAR(64) DEFAULT '',
    name VARCHAR(100) NOT NULL,
    category VARCHAR(30) NOT NULL DEFAULT 'feature',
    path VARCHAR(500) DEFAULT '',
    campaign_id UUID,
    duration_ms INTEGER,
    properties JSONB DEFAULT '{}',
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_product_event_org_occurred ON product_event(org_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_product_event_name_occurred ON product_event(name, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_product_event_user_occurred ON product_event(user_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_product_event_campaign ON product_event(campaign_id);
CREATE INDEX IF NOT EXISTS idx_product_event_session ON product_event(session_id);

-- Outbound webhooks: tenant-registered HTTP endpoints + per-attempt delivery log.
-- `secret` is the HMAC-SHA256 signing key handed to the customer once at
-- registration; the receiver needs the same value to verify X-Webhook-Signature.
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
-- In-app notifications (backend/src/agency/routers/notifications.py).
--
-- Declared in models/tables.py since it was written but never added here, so no
-- provisioned database has ever had it and every notifications route 500'd in
-- production. Scoped by BOTH user_id and org_id: user_id is the narrower key,
-- org_id is carried so the rows obey the same tenant filter as everything else.
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

-- The bell polls unread-per-user constantly; the partial index keeps that off a
-- full scan as the table grows.
CREATE INDEX IF NOT EXISTS idx_notification_user_created
    ON notification(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notification_user_unread
    ON notification(user_id) WHERE read = FALSE;
CREATE INDEX IF NOT EXISTS idx_notification_org ON notification(org_id);

-- ---------------------------------------------------------------------------
-- RAG knowledge base (backend/src/agency/services/knowledge_base.py).
--
-- pgvector is an OPTIONAL prerequisite, created defensively on purpose:
--   * Neon supports the `vector` extension but it must be enabled per database;
--     whether it is enabled on this deployment's Neon branch is NOT verifiable
--     from this repo — the operator must run `CREATE EXTENSION IF NOT EXISTS
--     vector;` once and confirm `SELECT extname FROM pg_extension`.
--   * the `postgres:16-alpine` image in docker/docker-compose.yml does not ship
--     pgvector at all, so an unguarded CREATE EXTENSION would abort this whole
--     init script and break local bootstrap.
-- If the extension is missing, the table is skipped and knowledge_base.py
-- degrades to keyword retrieval, labelled `retrieval_mode: "keyword"` in every
-- response. It never pretends to be semantic.
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
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        RETURN;
    END IF;

    -- embedding is vector(1536) for every provider; shorter vectors (Google's
    -- 768) are zero-padded by the writer. Padding both operands with the same
    -- trailing zeros leaves cosine similarity exactly unchanged. embedding_dim
    -- keeps the true width, and queries filter on embedding_model so vectors
    -- from two providers are never compared.
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
    -- HNSW over cosine distance (<=>), matching the ORDER BY in the retriever.
    CREATE INDEX IF NOT EXISTS idx_knowledge_embedding_cosine
        ON knowledge_embedding USING hnsw (embedding vector_cosine_ops);
END
$$;

-- ---------------------------------------------------------------------------
-- Composite indexes for the hot read paths.
--
-- Postgres can bitmap-AND two single-column indexes, but these three queries
-- run often enough to deserve a direct match:
--   * the scheduler sweeps (status, scheduled_at) across every org once a
--     minute, forever — this is the highest-frequency query in the system;
--   * the content and campaign list endpoints both filter (org_id, status).
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_content_piece_due
    ON content_piece(status, scheduled_at)
    WHERE status = 'scheduled';
CREATE INDEX IF NOT EXISTS idx_content_piece_org_status
    ON content_piece(org_id, status);
CREATE INDEX IF NOT EXISTS idx_campaign_org_status
    ON campaign(org_id, status);
