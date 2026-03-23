const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options?.headers,
    },
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body.detail || "Request failed");
  }
  return res.json();
}

export const api = {
  health: () => request<{ status: string }>("/api/v1/health"),

  login: (email: string, password: string) =>
    request<{ access_token: string; role: string; org_id: string }>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  signup: (data: { email: string; password: string; full_name: string; org_name: string }) =>
    request<{ access_token: string; role: string; org_id: string }>("/api/v1/auth/signup", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  getClients: (page = 1) => request<ClientListResponse>(`/api/v1/clients?page=${page}`),
  getClient: (id: string) => request<Client>(`/api/v1/clients/${id}`),
  createClient: (data: CreateClientRequest) =>
    request<Client>("/api/v1/clients", { method: "POST", body: JSON.stringify(data) }),

  createBrandProfile: (clientId: string, data: BrandProfileRequest) =>
    request(`/api/v1/clients/${clientId}/brand-profile`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  getCampaigns: (clientId?: string) =>
    request<CampaignListResponse>(
      `/api/v1/campaigns${clientId ? `?client_id=${clientId}` : ""}`
    ),
  getCampaign: (id: string) => request<Campaign>(`/api/v1/campaigns/${id}`),
  createCampaign: (data: CampaignBriefRequest) =>
    request<Campaign>("/api/v1/campaigns", { method: "POST", body: JSON.stringify(data) }),

  getCampaignContent: (campaignId: string) =>
    request<{ items: ContentPiece[]; total: number }>(`/api/v1/campaigns/${campaignId}/content`),

  submitReview: (campaignId: string, decision: string, feedback?: string) =>
    request(`/api/v1/campaigns/${campaignId}/review`, {
      method: "PATCH",
      body: JSON.stringify({ decision, feedback }),
    }),

  getContent: (params?: Record<string, string>) => {
    const qs = params ? `?${new URLSearchParams(params)}` : "";
    return request<{ items: ContentPiece[]; total: number }>(`/api/v1/content${qs}`);
  },
  updateContent: (id: string, data: Partial<ContentPiece>) =>
    request<ContentPiece>(`/api/v1/content/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  approveContent: (id: string) =>
    request(`/api/v1/content/${id}/approve`, { method: "POST" }),

  getStats: () => request<DashboardStats>("/api/v1/stats"),

  extractBrand: (url: string) =>
    request<BrandProfile>("/api/v1/magic-brief", {
      method: "POST",
      body: JSON.stringify({ url }),
    }),

  getCalendar: async (start: string, end: string) => {
    const data = await request<CalendarApiResponse>(
      `/api/v1/publishing/calendar?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`
    );
    const items = Array.isArray(data) ? data : data.items ?? [];
    return { items };
  },

  scheduleContent: (contentId: string, scheduledAt: string) =>
    request(`/api/v1/publishing/${contentId}/schedule`, {
      method: "POST",
      body: JSON.stringify({ scheduled_at: scheduledAt }),
    }),

  publishContent: (contentId: string) =>
    request(`/api/v1/publishing/${contentId}/publish`, { method: "POST" }),

  getPlans: async () => {
    const data = await request<Plan[] | { items: Plan[]; plans?: Plan[] }>("/api/v1/billing/plans");
    if (Array.isArray(data)) return data;
    return data.items ?? data.plans ?? [];
  },

  getSubscription: () => request<SubscriptionInfo>("/api/v1/billing/subscription"),

  createCheckout: (planTier: string) =>
    request<{ checkout_url: string; session_id?: string }>("/api/v1/billing/checkout", {
      method: "POST",
      body: JSON.stringify({ plan_tier: planTier }),
    }),

  getTeam: async () => {
    const data = await request<TeamMember[] | { items: TeamMember[]; members?: TeamMember[] }>(
      "/api/v1/team"
    );
    if (Array.isArray(data)) return data;
    if ("items" in data && Array.isArray(data.items)) return data.items;
    if ("members" in data && Array.isArray(data.members)) return data.members;
    return [];
  },

  inviteTeamMember: (email: string, role: string) =>
    request("/api/v1/team/invite", {
      method: "POST",
      body: JSON.stringify({ email, role }),
    }),
};

// --- Types ---

export interface Client {
  id: string;
  org_id: string;
  brand_name: string;
  industry: string | null;
  description: string;
  website_url: string | null;
  contact_email: string | null;
  logo_url: string | null;
  is_active: boolean;
  created_at: string;
}

export interface ClientListResponse {
  items: Client[];
  total: number;
  page: number;
  per_page: number;
}

export interface CreateClientRequest {
  brand_name: string;
  industry: string;
  description?: string;
  website_url?: string;
  contact_email?: string;
}

export interface BrandProfileRequest {
  voice_description: string;
  tone_attributes: Record<string, number>;
  target_audience: string;
  style_rules: string[];
  emoji_policy: string;
}

export interface Campaign {
  id: string;
  client_id: string;
  org_id: string;
  name: string;
  objective: string;
  channels: string[];
  start_date: string;
  end_date: string;
  budget: Record<string, any>;
  status: string;
  agent_plan: Record<string, any>;
  created_at: string;
}

export interface CampaignListResponse {
  items: Campaign[];
  total: number;
  page: number;
  per_page: number;
}

export interface CampaignBriefRequest {
  client_id: string;
  campaign_name: string;
  objective: string;
  channels: string[];
  target_audience?: string;
  key_messages?: string[];
  budget_usd?: number;
  start_date: string;
  end_date: string;
  additional_context?: string;
}

export interface ContentPiece {
  id: string;
  campaign_id: string | null;
  client_id: string;
  content_type: string;
  platform: string;
  title: string;
  body: string;
  hashtags: string[];
  status: string;
  ai_generated: boolean;
  performance_score: number | null;
  created_at: string;
}

export interface DashboardStats {
  total_clients: number;
  total_campaigns: number;
  total_content_pieces: number;
  total_agent_runs: number;
  campaigns_running: number;
  content_drafts: number;
}

export interface AgentStreamEvent {
  type: "step_start" | "step_update" | "step_complete" | "waiting_human" | "error" | "complete" | "heartbeat";
  agent: string;
  content: string;
  progress: number;
  timestamp: string;
}

export interface BrandProfile {
  brand_name?: string;
  industry?: string;
  description?: string;
  voice_description?: string;
  tone_attributes?: Record<string, number>;
  target_audience?: string;
  style_rules?: string[];
  emoji_policy?: string;
  source_url?: string;
  error?: string;
  vocabulary_include?: string[];
  vocabulary_exclude?: string[];
  suggested_channels?: string[];
  content_pillars?: string[];
  competitor_differentiation?: string;
}

export interface CalendarEntry {
  id: string;
  title: string;
  platform: string;
  scheduled_at: string | null;
  status: string;
  body?: string;
  campaign_id?: string | null;
  client_id?: string;
  content_type?: string;
}

export type CalendarApiResponse = CalendarEntry[] | { items: CalendarEntry[] };

export interface Plan {
  tier: string;
  price_id?: string;
  clients_limit?: number;
  posts_limit?: number;
  features?: string[];
  amount?: number;
}

export interface SubscriptionInfo {
  plan_tier: string;
  status?: string;
  clients_limit?: number;
  posts_limit?: number;
  posts_used?: number;
  features?: string[];
}

export interface TeamMember {
  id: string;
  email: string;
  full_name: string;
  role: string;
  is_active?: boolean;
  permissions?: string[];
  created_at?: string | null;
}
