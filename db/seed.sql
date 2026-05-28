-- CampaignForge demo / IntelliForge showcase data
--
-- Docker: applied automatically after init.sql (see docker-compose).
-- Manual: psql "$DATABASE_URL" -f db/seed.sql
--
-- Who sees this data?
-- 1) JWT login (no Clerk): POST /auth/login as admin@campaignforge.ai / password123
-- 2) Clerk + same email: existing seeded User row matches Clerk primary email → uses demo org.
-- 3) Clerk + your email: set backend env DEMO_ORG_ID + DEMO_ORG_ALLOWLIST (see .env.example).
--
-- Demo org id (referenced by DEMO_ORG_ID):
-- a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11

-- Demo Organization
INSERT INTO organization (id, name, domain) VALUES
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'CampaignForge Demo', 'demo.campaignforge.ai')
ON CONFLICT (id) DO NOTHING;

-- Demo Users (password: "password123" — bcrypt hash; JWT / legacy auth only)
INSERT INTO users (org_id, email, password_hash, full_name, role) VALUES
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'admin@campaignforge.ai',
 '$2b$12$LJ3xFjGLGnBBkYG.ILdte.XqFgjlOe3MihOb.pBFqHHKkYN8wLyOi',
 'Admin User', 'admin'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'creator@campaignforge.ai',
 '$2b$12$LJ3xFjGLGnBBkYG.ILdte.XqFgjlOe3MihOb.pBFqHHKkYN8wLyOi',
 'Content Creator', 'content_creator')
ON CONFLICT (email) DO NOTHING;

-- Demo Subscription (one row per org)
INSERT INTO subscription (org_id, plan_tier, clients_limit, posts_limit, status)
SELECT 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'starter', 10, 200, 'active'
WHERE NOT EXISTS (
  SELECT 1 FROM subscription WHERE org_id = 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'::uuid
);

-- Demo Clients
INSERT INTO client (id, org_id, brand_name, industry, description, website_url) VALUES
('b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a22', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
 'Sunrise Coffee', 'Food & Beverage',
 'Local artisan coffee roaster with 3 locations. Organic, fair-trade beans. Community-driven brand.',
 'https://sunrisecoffee.example.com'),
('b2eebc99-9c0b-4ef8-bb6d-6bb9bd380a33', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
 'NovaTech SaaS', 'Technology',
 'B2B project management platform for remote teams. Focus on async communication and AI features.',
 'https://novatech.example.com'),
('b3eebc99-9c0b-4ef8-bb6d-6bb9bd380a44', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
 'GreenLeaf Clinic', 'Healthcare',
 'Modern wellness clinic offering holistic healthcare services. Targets health-conscious millennials.',
 'https://greenleaf.example.com'),
('b4eebc99-9c0b-4ef8-bb6d-6bb9bd380a55', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
 'Bella Cucina', 'Restaurant',
 'Farm-to-table Italian restaurant. Known for seasonal menus and wine pairing events.',
 'https://bellacucina.example.com'),
('b5eebc99-9c0b-4ef8-bb6d-6bb9bd380a66', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
 'IntelliForge AI', 'AI Services',
 'Hyderabad-based AI agent development and workflow automation — from prompt engineering to production AI apps. Aligned with Bharat AI Mission.',
 'https://www.intelliforge.tech/')
ON CONFLICT (id) DO NOTHING;

-- Demo Brand Profiles
INSERT INTO brand_profile (client_id, org_id, voice_description, tone_attributes, target_audience, style_rules, competitor_differentiation) VALUES
('b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a22', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
 'Warm, community-focused, passionate about craft coffee. Friendly and approachable.',
 '{"formality": 0.3, "humor": 0.5, "warmth": 0.9, "urgency": 0.2}',
 'Coffee enthusiasts, millennials 25-40, local community members, health-conscious consumers',
 ARRAY['Use first-person plural (we, our)', 'Include sensory descriptions', 'Always mention sustainability'],
 ''),
('b2eebc99-9c0b-4ef8-bb6d-6bb9bd380a33', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
 'Professional, innovative, forward-thinking. Data-driven but human-centered.',
 '{"formality": 0.7, "humor": 0.2, "authority": 0.8, "urgency": 0.4}',
 'Remote team leaders, CTOs, project managers at companies 50-500 employees',
 ARRAY['Lead with data and results', 'Use active voice', 'Avoid jargon without explanation'],
 ''),
('b3eebc99-9c0b-4ef8-bb6d-6bb9bd380a44', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
 'Caring, expert, reassuring. Balance medical authority with accessible language.',
 '{"formality": 0.6, "empathy": 0.9, "authority": 0.7, "urgency": 0.3}',
 'Health-conscious millennials 28-42, parents, wellness seekers in urban areas',
 ARRAY['Never make medical claims without qualifiers', 'Use inclusive language', 'Focus on wellness over illness'],
 ''),
('b4eebc99-9c0b-4ef8-bb6d-6bb9bd380a55', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
 'Elegant, passionate, inviting. Celebrates Italian food culture and seasonal ingredients.',
 '{"formality": 0.5, "passion": 0.9, "elegance": 0.8, "warmth": 0.7}',
 'Foodies 30-55, date-night couples, wine enthusiasts, local fine-dining seekers',
 ARRAY['Use Italian culinary terms with translations', 'Emphasize freshness and seasonality', 'Include sensory descriptions of dishes'],
 ''),
('b5eebc99-9c0b-4ef8-bb6d-6bb9bd380a66', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
 'Expert, approachable, India-first enterprise credibility. Clear on outcomes; minimal hype. Responsible AI and human-in-the-loop where it matters.',
 '{"formality": 0.65, "authority": 0.85, "warmth": 0.5, "urgency": 0.35}',
 'Startup founders, SaaS leaders, enterprise innovation teams in India and globally seeking AI agents, automation, and shipped AI applications.',
 ARRAY['Reference the 5-level AI framework when relevant', 'Tie claims to services: agents, workflows, apps', 'Prefer proof (portfolio, process) over generic AI buzzwords'],
 'Full-stack AI partner (training → automation → agents → apps) vs single-point copy or SEO-only tools.')
ON CONFLICT (client_id) DO NOTHING;

-- Platform accounts (for client context / calendar integrations)
INSERT INTO platform_account (id, client_id, org_id, platform, account_handle, display_name, followers_count, status) VALUES
('c0aaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa01', 'b5eebc99-9c0b-4ef8-bb6d-6bb9bd380a66', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
 'linkedin', 'intelliforge-ai', 'IntelliForge AI', 1200, 'connected'),
('c0aaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa02', 'b5eebc99-9c0b-4ef8-bb6d-6bb9bd380a66', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
 'twitter', 'IntelliForgeAI', 'IntelliForge AI', 800, 'connected')
ON CONFLICT (id) DO NOTHING;

-- Campaigns (statuses + dates illustrate list + detail UI)
INSERT INTO campaign (id, client_id, org_id, name, objective, channels, start_date, end_date, budget, status, agent_plan, tags) VALUES
(
  'd0111111-1111-4111-8111-111111111101',
  'b5eebc99-9c0b-4ef8-bb6d-6bb9bd380a66',
  'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
  'IntelliForge — Q2 B2B demand gen',
  'Drive qualified strategy calls and roadmap requests for AI agents, workflow automation, and AI app builds. Emphasize enterprise depth and Bharat AI Mission alignment.',
  ARRAY['linkedin', 'twitter']::text[],
  '2026-04-01', '2026-06-30',
  '{"total_usd": 2500}'::jsonb,
  'completed',
  '{"pipeline_version": "langgraph-v1", "nodes_completed": ["orchestrate", "strategise", "seo_research", "create_content", "write_ads", "human_review", "qa_check", "compile_output", "analytics"]}'::jsonb,
  '["b2b", "intelliforge", "demo"]'::jsonb
),
(
  'd0222222-2222-4222-8222-222222222202',
  'b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a22',
  'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
  'Sunrise Coffee — Spring menu launch',
  'Promote seasonal drinks and community events across Instagram and Facebook.',
  ARRAY['instagram', 'facebook']::text[],
  '2026-03-15', '2026-05-15',
  '{"total_usd": 800}'::jsonb,
  'completed',
  '{}'::jsonb,
  '["retail", "demo"]'::jsonb
),
(
  'd0333333-3333-4333-8333-333333333303',
  'b2eebc99-9c0b-4ef8-bb6d-6bb9bd380a33',
  'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
  'NovaTech — Product Hunt prep',
  'Draft social proof and launch messaging for an upcoming Product Hunt campaign.',
  ARRAY['linkedin', 'twitter']::text[],
  '2026-05-01', '2026-05-20',
  '{"total_usd": 400}'::jsonb,
  'planning',
  '{}'::jsonb,
  '["saas", "demo"]'::jsonb
)
ON CONFLICT (id) DO NOTHING;

-- Workflows (completed runs for finished campaigns)
INSERT INTO workflow (id, campaign_id, org_id, current_node, status, total_duration_ms, total_cost_usd, completed_at) VALUES
(
  'e0bbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbb01',
  'd0111111-1111-4111-8111-111111111101',
  'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
  'analytics',
  'completed',
  145000,
  0.42,
  '2026-04-10T18:30:00Z'
),
(
  'e0bbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbb02',
  'd0222222-2222-4222-8222-222222222202',
  'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
  'analytics',
  'completed',
  98000,
  0.28,
  '2026-03-28T14:00:00Z'
)
ON CONFLICT (id) DO NOTHING;

-- Agent runs (mirror LangGraph node names from graph.py)
INSERT INTO agent_run (id, campaign_id, org_id, agent_name, input_summary, output, tokens_used, model_used, duration_ms, cost_usd, status) VALUES
('f0cccccc-cccc-4ccc-8ccc-cccccccccc01', 'd0111111-1111-4111-8111-111111111101', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
 'orchestrate', 'Brief: B2B demand gen for AI services', '{"current_agent": "orchestrate", "status": "running"}', 420, 'claude-3-5-sonnet', 8200, 0.018, 'completed'),
('f0cccccc-cccc-4ccc-8ccc-cccccccccc02', 'd0111111-1111-4111-8111-111111111101', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
 'strategise', 'Positioning vs generic AI agencies', '{"pillars": ["agents", "workflows", "apps"], "icp": "B2B + India"}', 1100, 'claude-3-5-sonnet', 12000, 0.032, 'completed'),
('f0cccccc-cccc-4ccc-8ccc-cccccccccc03', 'd0111111-1111-4111-8111-111111111101', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
 'seo_research', 'Keywords: AI agents India, workflow automation', '{"seeds": ["ai agent development", "workflow automation", "bharat ai"]}', 900, 'gemini-2.0-flash', 9000, 0.006, 'completed'),
('f0cccccc-cccc-4ccc-8ccc-cccccccccc04', 'd0111111-1111-4111-8111-111111111101', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
 'create_content', 'LinkedIn + X posts', '{"content_pieces": 2}', 2100, 'gemini-2.0-flash', 15000, 0.014, 'completed'),
('f0cccccc-cccc-4ccc-8ccc-cccccccccc05', 'd0111111-1111-4111-8111-111111111101', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
 'write_ads', 'Short-form ad variants', '{"ad_variants": 2}', 800, 'gemini-2.0-flash', 11000, 0.005, 'completed'),
('f0cccccc-cccc-4ccc-8ccc-cccccccccc06', 'd0111111-1111-4111-8111-111111111101', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
 'human_review', 'Approver checkpoint', '{"human_review": "approved"}', 0, '', 0, 0, 'completed'),
('f0cccccc-cccc-4ccc-8ccc-cccccccccc07', 'd0111111-1111-4111-8111-111111111101', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
 'qa_check', 'Brand + policy QA', '{"pass": true}', 600, 'claude-3-5-sonnet', 7000, 0.019, 'completed'),
('f0cccccc-cccc-4ccc-8ccc-cccccccccc08', 'd0111111-1111-4111-8111-111111111101', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
 'compile_output', 'Package deliverables', '{"status": "completed"}', 200, 'claude-3-5-sonnet', 3000, 0.008, 'completed'),
('f0cccccc-cccc-4ccc-8ccc-cccccccccc09', 'd0111111-1111-4111-8111-111111111101', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
 'analytics', 'Suggested KPIs', '{"kpis": ["CTR", "MQLs", "booked calls"]}', 400, 'gemini-2.0-flash', 5000, 0.003, 'completed'),
('f0cccccc-cccc-4ccc-8ccc-cccccccccc10', 'd0222222-2222-4222-8222-222222222202', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
 'orchestrate', 'Spring menu launch', '{"current_agent": "orchestrate"}', 380, 'claude-3-5-sonnet', 7500, 0.015, 'completed'),
('f0cccccc-cccc-4ccc-8ccc-cccccccccc11', 'd0222222-2222-4222-8222-222222222202', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
 'create_content', 'IG / FB captions', '{"content_pieces": 2}', 1500, 'gemini-2.0-flash', 13000, 0.011, 'completed')
ON CONFLICT (id) DO NOTHING;

-- Content pieces (campaign detail → Content tab)
INSERT INTO content_piece (id, campaign_id, client_id, org_id, agent_run_id, content_type, platform, title, body, hashtags, "metadata", ai_generated, status) VALUES
(
  'a0dddddd-dddd-4ddd-8ddd-dddddddddd01',
  'd0111111-1111-4111-8111-111111111101',
  'b5eebc99-9c0b-4ef8-bb6d-6bb9bd380a66',
  'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
  'f0cccccc-cccc-4ccc-8ccc-cccccccccc04',
  'social_post',
  'linkedin',
  'From foundations to shipped AI apps',
  'Most teams do not need another generic chatbot—they need agents, workflows, and apps tied to business outcomes. We map maturity across five levels so you invest in the right step next (not the loudest vendor pitch). Book a free strategy call if you want a practical roadmap.',
  '["AIAgents", "WorkflowAutomation", "IndiaAI"]'::jsonb,
  '{"angle": "thought_leadership"}'::jsonb,
  TRUE,
  'draft'
),
(
  'a0dddddd-dddd-4ddd-8ddd-dddddddddd02',
  'd0111111-1111-4111-8111-111111111101',
  'b5eebc99-9c0b-4ef8-bb6d-6bb9bd380a66',
  'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
  'f0cccccc-cccc-4ccc-8ccc-cccccccccc04',
  'social_post',
  'twitter',
  'Ship AI apps in weeks, not months',
  'Agent systems + vibe-coded apps—when the stack matches the problem. Hyderabad → global. Aligned with Bharat AI Mission.',
  '["BuildInPublic", "AI", "Agents"]'::jsonb,
  '{}'::jsonb,
  TRUE,
  'approved'
),
(
  'a0dddddd-dddd-4ddd-8ddd-dddddddddd03',
  'd0111111-1111-4111-8111-111111111101',
  'b5eebc99-9c0b-4ef8-bb6d-6bb9bd380a66',
  'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
  'f0cccccc-cccc-4ccc-8ccc-cccccccccc05',
  'social_post',
  'linkedin',
  'Ad variant A — enterprise',
  'Headline: Production-grade AI agents with human oversight. Sub: Banking, pharma, telecom, SaaS—13+ years shipping under compliance pressure. CTA: Get your AI roadmap.',
  '[]'::jsonb,
  '{"variant": "A"}'::jsonb,
  TRUE,
  'draft'
),
(
  'a0dddddd-dddd-4ddd-8ddd-dddddddddd04',
  'd0222222-2222-4222-8222-222222222202',
  'b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a22',
  'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
  'f0cccccc-cccc-4ccc-8ccc-cccccccccc11',
  'social_post',
  'instagram',
  'Spring lavender latte is back',
  'Light floral notes, oat or dairy, best enjoyed on the patio. Three cafes, same roast quality. Tag a friend you owe a coffee date.',
  '["SunriseCoffee", "SpringMenu", "SpecialtyCoffee"]'::jsonb,
  '{}'::jsonb,
  TRUE,
  'approved'
),
(
  'a0dddddd-dddd-4ddd-8ddd-dddddddddd05',
  'd0222222-2222-4222-8222-222222222202',
  'b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a22',
  'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
  NULL,
  'social_post',
  'facebook',
  'Weekend cupping event',
  'Join us Saturday 10am for a free cupping—learn how we source fair-trade beans and take home a sample bag (while supplies last).',
  '[]'::jsonb,
  '{}'::jsonb,
  TRUE,
  'draft'
)
ON CONFLICT (id) DO NOTHING;

-- Campaign Templates
INSERT INTO campaign_template (org_id, name, description, category, objective_template, channels, is_public) VALUES
(NULL, 'Product Launch', 'Complete multi-platform launch campaign with awareness, engagement, and conversion phases', 'launch', 'Launch [PRODUCT] to [AUDIENCE] across social channels, driving awareness and sign-ups', ARRAY['linkedin', 'twitter', 'instagram'], TRUE),
(NULL, 'Weekly Social Calendar', 'Recurring weekly content plan with daily themes', 'recurring', 'Maintain consistent brand presence with 5 posts per week across primary channels', ARRAY['linkedin', 'twitter'], TRUE),
(NULL, 'Brand Awareness', 'Top-of-funnel campaign focused on reach and impressions', 'awareness', 'Increase brand awareness among [AUDIENCE] by 30% over 4 weeks', ARRAY['instagram', 'facebook', 'twitter'], TRUE),
(NULL, 'Thought Leadership', 'B2B-focused LinkedIn and Twitter campaign for authority building', 'b2b', 'Establish [BRAND] as a thought leader in [INDUSTRY] through expert content', ARRAY['linkedin', 'twitter'], TRUE),
(NULL, 'Holiday Campaign', 'Seasonal campaign template with festive messaging', 'seasonal', 'Drive holiday engagement and sales with festive, time-sensitive content', ARRAY['instagram', 'facebook', 'twitter'], TRUE),
(NULL, 'Event Promotion', 'Pre-event, during-event, and post-event content plan', 'events', 'Maximize attendance and engagement for [EVENT] across all channels', ARRAY['linkedin', 'twitter', 'instagram'], TRUE)
ON CONFLICT DO NOTHING;
