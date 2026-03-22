-- Demo Organization
INSERT INTO organization (id, name, domain) VALUES
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'CampaignForge Demo', 'demo.campaignforge.ai')
ON CONFLICT (id) DO NOTHING;

-- Demo Users (password: "password123" — bcrypt hash)
INSERT INTO users (org_id, email, password_hash, full_name, role) VALUES
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'admin@campaignforge.ai',
 '$2b$12$LJ3xFjGLGnBBkYG.ILdte.XqFgjlOe3MihOb.pBFqHHKkYN8wLyOi',
 'Admin User', 'admin'),
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'creator@campaignforge.ai',
 '$2b$12$LJ3xFjGLGnBBkYG.ILdte.XqFgjlOe3MihOb.pBFqHHKkYN8wLyOi',
 'Content Creator', 'content_creator')
ON CONFLICT (email) DO NOTHING;

-- Demo Subscription
INSERT INTO subscription (org_id, plan_tier, clients_limit, posts_limit, status) VALUES
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'starter', 10, 200, 'active')
ON CONFLICT DO NOTHING;

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
 'https://bellacucina.example.com')
ON CONFLICT (id) DO NOTHING;

-- Demo Brand Profiles
INSERT INTO brand_profile (client_id, org_id, voice_description, tone_attributes, target_audience, style_rules) VALUES
('b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a22', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
 'Warm, community-focused, passionate about craft coffee. Friendly and approachable.',
 '{"formality": 0.3, "humor": 0.5, "warmth": 0.9, "urgency": 0.2}',
 'Coffee enthusiasts, millennials 25-40, local community members, health-conscious consumers',
 ARRAY['Use first-person plural (we, our)', 'Include sensory descriptions', 'Always mention sustainability']),
('b2eebc99-9c0b-4ef8-bb6d-6bb9bd380a33', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
 'Professional, innovative, forward-thinking. Data-driven but human-centered.',
 '{"formality": 0.7, "humor": 0.2, "authority": 0.8, "urgency": 0.4}',
 'Remote team leaders, CTOs, project managers at companies 50-500 employees',
 ARRAY['Lead with data and results', 'Use active voice', 'Avoid jargon without explanation']),
('b3eebc99-9c0b-4ef8-bb6d-6bb9bd380a44', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
 'Caring, expert, reassuring. Balance medical authority with accessible language.',
 '{"formality": 0.6, "empathy": 0.9, "authority": 0.7, "urgency": 0.3}',
 'Health-conscious millennials 28-42, parents, wellness seekers in urban areas',
 ARRAY['Never make medical claims without qualifiers', 'Use inclusive language', 'Focus on wellness over illness']),
('b4eebc99-9c0b-4ef8-bb6d-6bb9bd380a55', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
 'Elegant, passionate, inviting. Celebrates Italian food culture and seasonal ingredients.',
 '{"formality": 0.5, "passion": 0.9, "elegance": 0.8, "warmth": 0.7}',
 'Foodies 30-55, date-night couples, wine enthusiasts, local fine-dining seekers',
 ARRAY['Use Italian culinary terms with translations', 'Emphasize freshness and seasonality', 'Include sensory descriptions of dishes'])
ON CONFLICT DO NOTHING;
