CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE SCHEMA IF NOT EXISTS campaignforge;

-- Organizations (tenants)
CREATE TABLE IF NOT EXISTS organization (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
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
