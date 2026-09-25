const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

/**
 * A non-2xx response. `detail` is FastAPI's `detail` exactly as sent — usually
 * a string, but structured for errors the UI branches on (e.g. `{code: ...}`).
 * `message` is always a readable string, so `err.message` callers keep working.
 */
export class ApiError extends Error {
  constructor(public status: number, message: string, public detail: unknown = message) {
    super(message);
  }
}

function detailMessage(detail: unknown): string {
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail) && typeof detail[0]?.msg === "string") return detail[0].msg;
  if (detail && typeof detail === "object") {
    const d = detail as { message?: unknown; code?: unknown };
    if (typeof d.message === "string") return d.message;
    if (typeof d.code === "string") return d.code.replace(/_/g, " ");
  }
  return "Request failed";
}

let _clerkGetToken: (() => Promise<string | null>) | null = null;

/*
 * Clerk readiness gate.
 *
 * `getToken()` resolves `null` until Clerk has hydrated the session, and every
 * dashboard screen fires its fetches from a mount effect. Without this gate the
 * first render of a freshly signed-up user raced Clerk and lost: the requests
 * went out with **no** Authorization header at all, the API answered 401 (which
 * is correct — there was no credential), and providers like ActiveClientProvider
 * latched `error: true` with no retry, so the app stayed broken until a manual
 * reload. It reproduced hardest for new users because their session is created
 * in the same navigation that renders the dashboard.
 *
 * So: never fire an authenticated request while the token is merely *not ready
 * yet*. Wait for Clerk to report `isLoaded`, then read the token.
 */
let _authReady = false;
let _markAuthReady = () => {};
const _authReadyPromise = new Promise<void>((resolve) => {
  _markAuthReady = resolve;
});

/** Cap on how long a request waits for Clerk. Only ever hit if Clerk never loads
 * (blocked script, offline) — the request then proceeds unauthenticated and 401s,
 * which is the honest outcome rather than a hang. */
const AUTH_READY_TIMEOUT_MS = 8000;

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

/**
 * Called from ClerkTokenSync to wire up Clerk's getToken.
 *
 * `ready` is Clerk's `isLoaded`. Signed **out** counts as ready: `getToken()`
 * legitimately returns null there, and requests should go out unauthenticated
 * rather than stall for the timeout.
 */
export function setClerkTokenGetter(
  getter: () => Promise<string | null>,
  ready = true
) {
  _clerkGetToken = getter;
  if (ready && !_authReady) {
    _authReady = true;
    _markAuthReady();
  }
}

/** Base URL and token, for callers that need their own fetch (e.g. keepalive). */
export const API_BASE_URL = API_BASE;

/** The bearer token, waiting for Clerk to hydrate rather than returning a
 * premature null. Returns null only when genuinely signed out or Clerk never
 * loaded. */
export async function getAuthToken(): Promise<string | null> {
  if (!_authReady) {
    await Promise.race([_authReadyPromise, sleep(AUTH_READY_TIMEOUT_MS)]);
  }
  return _clerkGetToken ? await _clerkGetToken() : null;
}

async function unwrap<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, detailMessage(body.detail), body.detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const token = await getAuthToken();

  const send = (bearer: string | null) =>
    fetch(`${API_BASE}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(bearer ? { Authorization: `Bearer ${bearer}` } : {}),
        ...options?.headers,
      },
    });

  let res = await send(token);

  // Safety net for the narrow window the readiness gate cannot cover: Clerk
  // reported loaded but handed back a token that was null or had just expired
  // (its session tokens are short-lived and refreshed lazily). Only retried when
  // the first attempt was unauthenticated or the server rejected the credential,
  // and only once, so a genuinely signed-out caller still fails fast.
  if (res.status === 401 && _clerkGetToken) {
    const fresh = await _clerkGetToken().catch(() => null);
    if (fresh && fresh !== token) res = await send(fresh);
  }

  return unwrap<T>(res);
}

/**
 * Unauthenticated fetch — deliberately attaches **no** bearer token.
 *
 * The client-portal routes (`/api/v1/portal/...`) are public by design: a
 * client of an agency reviews content there without a CampaignForge login.
 * Sending an org token would be both useless and a needless credential leak to
 * a page that can be embedded on a custom domain.
 */
async function requestPublic<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  return unwrap<T>(res);
}

/**
 * Fetch authenticated with an org API key instead of a user bearer token.
 *
 * `ApiKeyAuthMiddleware` resolves `X-API-Key` into `request.state.api_key_org_id`
 * for `routers/public_api.py`. These routes exist so a customer can call the API
 * from their own backend; the methods below are here so an in-app "test your key"
 * flow can exercise them without a second HTTP client.
 */
async function requestWithApiKey<T>(
  path: string,
  apiKey: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": apiKey,
      ...options?.headers,
    },
  });
  return unwrap<T>(res);
}

/** Build a query string from defined values only. Returns "" when empty. */
export function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const search = new URLSearchParams();
  for (const key of Object.keys(params)) {
    const value = params[key];
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  }
  const out = search.toString();
  return out ? `?${out}` : "";
}

export const api = {
  // --- Health ---
  health: () => request<HealthResponse>("/api/v1/health"),
  healthDb: () => request<HealthDbResponse>("/api/v1/health/db"),
  /** Resolved provider/model per LLM tier. Authenticated; never returns key material. */
  healthLlm: () => request<LlmHealthResponse>("/api/v1/health/llm"),

  // --- Auth (local HS256 fallback) ---
  // Clerk is the production path and owns the token via setClerkTokenGetter().
  // These two exist for the dev/CI/e2e mode that logs in against db/seed.sql
  // users; the returned token is NOT installed into request() — the caller
  // decides what to do with it, so the Clerk indirection stays intact.
  login: (email: string, password: string) =>
    request<TokenResponse>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  signup: (data: SignupRequest) =>
    request<TokenResponse>("/api/v1/auth/signup", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // --- Clients ---
  getClients: (page = 1, archived = false) =>
    request<ClientListResponse>(`/api/v1/clients?page=${page}${archived ? "&archived=true" : ""}`),
  getClient: (id: string) => request<Client>(`/api/v1/clients/${id}`),
  createClient: (data: CreateClientRequest) =>
    request<Client>("/api/v1/clients", { method: "POST", body: JSON.stringify(data) }),

  /** Active and archived clients, for resolving names on campaigns and posts that
   * outlive an archive. Not for pickers — archived clients cannot take new work. */
  getClientsForLookup: async (): Promise<Client[]> => {
    const [active, archived] = await Promise.all([
      request<ClientListResponse>("/api/v1/clients?per_page=100"),
      request<ClientListResponse>("/api/v1/clients?per_page=100&archived=true"),
    ]);
    return [...active.items, ...archived.items];
  },
  /** 409 `has_scheduled_posts` while any of its posts are scheduled, unless `unschedule`,
   * which returns them to approved first. */
  archiveClient: (id: string, unschedule = false) =>
    request<Client>(`/api/v1/clients/${id}/archive${unschedule ? "?unschedule=true" : ""}`, { method: "POST" }),
  restoreClient: (id: string) => request<Client>(`/api/v1/clients/${id}/restore`, { method: "POST" }),
  updateClient: (id: string, data: UpdateClientRequest) =>
    request<Client>(`/api/v1/clients/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  getBrandProfile: (clientId: string) =>
    request<SavedBrandProfile>(`/api/v1/clients/${clientId}/brand-profile`),
  saveBrandProfile: (clientId: string, data: BrandProfileRequest) =>
    request<SavedBrandProfile>(`/api/v1/clients/${clientId}/brand-profile`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  createBrandProfile: (clientId: string, data: BrandProfileRequest) =>
    request<BrandProfileCreatedResponse>(`/api/v1/clients/${clientId}/brand-profile`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // --- Campaigns ---
  getCampaigns: (clientId?: string) =>
    request<CampaignListResponse>(
      `/api/v1/campaigns${clientId ? `?client_id=${clientId}` : ""}`
    ),
  getCampaign: (id: string) => request<Campaign>(`/api/v1/campaigns/${id}`),
  createCampaign: (data: CampaignBriefRequest) =>
    request<Campaign>("/api/v1/campaigns", { method: "POST", body: JSON.stringify(data) }),
  rerunCampaign: (id: string) =>
    request<Campaign>(`/api/v1/campaigns/${id}/rerun`, { method: "POST" }),

  getCampaignProgress: (id: string) =>
    request<CampaignProgress>(`/api/v1/campaigns/${id}/progress`),

  getCampaignContent: (campaignId: string) =>
    request<{ items: ContentPiece[]; total: number }>(`/api/v1/campaigns/${campaignId}/content`),

  submitReview: (campaignId: string, decision: ReviewDecision, feedback?: string) =>
    request<ReviewSubmittedResponse>(`/api/v1/campaigns/${campaignId}/review`, {
      method: "PATCH",
      body: JSON.stringify({ decision, feedback }),
    }),

  // GET /api/v1/campaigns/{id}/stream is intentionally absent: it is a
  // Server-Sent Events endpoint consumed by lib/agent-stream.ts, which needs an
  // EventSource (and the ?token= query param, since EventSource cannot set
  // headers). A fetch-based client method here would be wrong by construction.

  // --- Content ---
  getContent: (params?: ContentQuery) =>
    request<ContentListResponse>(`/api/v1/content${params ? qs({ ...params }) : ""}`),
  getContentPiece: (id: string) => request<ContentPiece>(`/api/v1/content/${id}`),
  updateContent: (id: string, data: ContentUpdateRequest) =>
    request<ContentPiece>(`/api/v1/content/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  approveContent: (id: string) =>
    request<ContentApprovedResponse>(`/api/v1/content/${id}/approve`, { method: "POST" }),

  /**
   * Engagement metrics for one content piece.
   *
   * `refresh` defaults to true server-side (a live platform fetch is attempted
   * first, capped at one per post per day). Pass `false` to read only what is
   * already stored.
   *
   * The response is a discriminated union on `status` — narrow before rendering.
   * See {@link ContentAnalyticsResponse} for the null-vs-zero contract.
   */
  getContentAnalytics: (contentId: string, refresh?: boolean) =>
    request<ContentAnalyticsResponse>(
      `/api/v1/content/${contentId}/analytics${refresh === undefined ? "" : qs({ refresh })}`
    ),

  getContentSuggestions: () =>
    request<{ items: ContentSuggestion[] }>("/api/v1/content/suggestions"),

  repurposeContent: (contentId: string, targetPlatforms: string[]) =>
    request<RepurposeResponse>(`/api/v1/content/${contentId}/repurpose`, {
      method: "POST",
      body: JSON.stringify({ target_platforms: targetPlatforms }),
    }),

  generateVariants: (contentId: string, count?: number) =>
    request<VariantsResponse>(`/api/v1/content/${contentId}/variants`, {
      method: "POST",
      body: JSON.stringify({ count: count ?? 2 }),
    }),

  generateImage: (contentId: string, prompt?: string, style?: string) =>
    request<GeneratedImageResponse>(`/api/v1/content/${contentId}/generate-image`, {
      method: "POST",
      body: JSON.stringify({ prompt, style }),
    }),

  createVideoScript: (data: VideoScriptRequest) =>
    request<VideoScriptResponse>("/api/v1/content/video-script", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // --- Stats ---
  getStats: () => request<DashboardStats>("/api/v1/stats"),

  // --- Magic Brief ---
  extractBrand: (url: string) =>
    request<BrandProfile>("/api/v1/magic-brief", {
      method: "POST",
      body: JSON.stringify({ url }),
    }),

  // --- Publishing ---
  getCalendar: async (start: string, end: string) => {
    const data = await request<CalendarApiResponse>(
      `/api/v1/publishing/calendar?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`
    );
    const items = Array.isArray(data) ? data : data.items ?? [];
    return { items };
  },

  scheduleContent: (contentId: string, scheduledAt: string) =>
    request<ScheduledResponse>(`/api/v1/publishing/${contentId}/schedule`, {
      method: "POST",
      body: JSON.stringify({ scheduled_at: scheduledAt }),
    }),

  publishContent: (contentId: string) =>
    request<PublishedResponse>(`/api/v1/publishing/${contentId}/publish`, { method: "POST" }),

  // Feature 12: Calendar reschedule — same endpoint as scheduleContent, kept as a
  // separate name because the calendar UI reads as "reschedule" at the call site.
  rescheduleContent: (contentId: string, scheduledAt: string) =>
    request<ScheduledResponse>(`/api/v1/publishing/${contentId}/schedule`, {
      method: "POST",
      body: JSON.stringify({ scheduled_at: scheduledAt }),
    }),

  // --- Billing ---
  getPlans: async () => {
    const data = await request<Plan[] | { items?: Plan[]; plans?: Plan[] }>("/api/v1/billing/plans");
    if (Array.isArray(data)) return data;
    return data.plans ?? data.items ?? [];
  },

  getSubscription: () => request<SubscriptionInfo>("/api/v1/billing/subscription"),

  createCheckout: (planTier: string, successUrl?: string, cancelUrl?: string) =>
    request<CheckoutResponse>("/api/v1/billing/checkout", {
      method: "POST",
      body: JSON.stringify({
        plan_tier: planTier,
        success_url: successUrl,
        cancel_url: cancelUrl,
      }),
    }),

  // POST /api/v1/billing/webhook is intentionally absent: it is Stripe's
  // server-to-server receiver, signature-verified against STRIPE_WEBHOOK_SECRET.
  // A browser can never produce a valid call.

  // --- Team ---
  getTeam: async () => {
    const data = await request<TeamMember[] | { items?: TeamMember[]; members?: TeamMember[] }>(
      "/api/v1/team"
    );
    if (Array.isArray(data)) return data;
    if (Array.isArray(data.members)) return data.members;
    if (Array.isArray(data.items)) return data.items;
    return [];
  },

  inviteTeamMember: (email: string, role: string) =>
    request<TeamInviteResponse>("/api/v1/team/invite", {
      method: "POST",
      body: JSON.stringify({ email, role }),
    }),

  updateTeamMemberRole: (userId: string, role: string) =>
    request<TeamMemberRoleResponse>(`/api/v1/team/${userId}/role`, {
      method: "PATCH",
      body: JSON.stringify({ role }),
    }),

  // --- Reports ---
  generateReport: (clientId: string, period: ReportPeriod) =>
    request<ClientReport>(`/api/v1/reports/clients/${clientId}`, {
      method: "POST",
      body: JSON.stringify({ period }),
    }),
  getReportPeriods: (clientId: string) =>
    request<{ items: ReportPeriodOption[] }>(`/api/v1/reports/clients/${clientId}`),

  // --- Organization settings ---
  getSettings: () => request<OrgSettings>("/api/v1/integrations/settings"),
  updateSettings: (data: OrgSettingsUpdate) =>
    request<OrgSettingsUpdatedResponse>("/api/v1/integrations/settings", {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  // --- API keys ---
  getApiKeys: () => request<{ items: ApiKeySummary[] }>("/api/v1/integrations/api-keys"),
  /** The plaintext `key` in the response is shown once and never again. */
  createApiKey: (name: string, permissions: string[]) =>
    request<ApiKeyCreatedResponse>("/api/v1/integrations/api-keys", {
      method: "POST",
      body: JSON.stringify({ name, permissions }),
    }),
  revokeApiKey: (keyId: string) =>
    request<{ status: string }>(`/api/v1/integrations/api-keys/${keyId}`, { method: "DELETE" }),

  getPlatformAccounts: () =>
    request<{ items: PlatformAccountSummary[] }>("/api/v1/integrations/platform-accounts"),

  // --- White label / branding ---
  /** Returns `{ is_active: false }` when the org has never configured branding. */
  getWhiteLabel: () => request<WhiteLabelResponse>("/api/v1/integrations/white-label"),
  updateWhiteLabel: (data: WhiteLabelUpdate) =>
    request<{ status: string }>("/api/v1/integrations/white-label", {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  // --- OAuth ---
  getOAuthUrl: (platform: string) =>
    request<OAuthAuthorizeResponse>(`/api/v1/oauth/${platform}/authorize`),
  oauthCallback: (platform: string, data: OAuthCallbackRequest) =>
    request<OAuthCallbackResponse>(`/api/v1/oauth/${platform}/callback`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  disconnectPlatformAccount: (platform: string, accountId: string) =>
    request<OAuthDisconnectResponse>(`/api/v1/oauth/${platform}/${accountId}`, {
      method: "DELETE",
    }),

  // --- Comments ---
  getComments: (contentId: string) =>
    request<{ items: ContentCommentItem[] }>(`/api/v1/comments/content/${contentId}`),
  addComment: (contentId: string, body: string) =>
    request<ContentCommentItem>(`/api/v1/comments/content/${contentId}`, {
      method: "POST",
      body: JSON.stringify({ body }),
    }),
  deleteComment: (commentId: string) =>
    request<{ status: string }>(`/api/v1/comments/${commentId}`, { method: "DELETE" }),

  // --- Notifications ---
  getNotifications: () =>
    request<{
      items: NotificationItem[];
      unread_count: number;
      /**
       * False while nothing in the backend calls `create_notification()`. The route has
       * always returned it; the client used to drop it on the floor. The bell reads it both
       * to explain an empty list honestly and to decide there is nothing worth re-fetching
       * for. Optional so an older backend simply reads as "assume producers exist".
       */
      producers_wired?: boolean;
      reason?: string;
    }>("/api/v1/notifications"),
  markNotificationRead: (id: string) =>
    request<{ status: string }>(`/api/v1/notifications/${id}/read`, { method: "PATCH" }),
  markAllNotificationsRead: () =>
    request<{ status: string }>("/api/v1/notifications/read-all", { method: "PATCH" }),

  // --- Campaign templates ---
  getTemplates: (category?: string) =>
    request<{ items: CampaignTemplateSummary[] }>(
      `/api/v1/integrations/templates${qs({ category })}`
    ),
  getTemplate: (id: string) =>
    request<CampaignTemplateDetail>(`/api/v1/integrations/templates/${id}`),
  createTemplate: (data: CampaignTemplateCreate) =>
    request<TemplateMutationResponse>("/api/v1/integrations/templates", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  /** Public templates only — the marketplace view, not this org's private ones. */
  getMarketplaceTemplates: (category?: string) =>
    request<{ items: MarketplaceTemplateSummary[] }>(
      `/api/v1/integrations/templates/marketplace${qs({ category })}`
    ),
  /** Clone a public template into this org. Returns the id of the new copy. */
  forkTemplate: (templateId: string) =>
    request<TemplateMutationResponse>(`/api/v1/integrations/templates/${templateId}/fork`, {
      method: "POST",
    }),
  /** Make one of this org's templates public on the marketplace. */
  publishTemplate: (templateId: string) =>
    request<TemplateMutationResponse>(`/api/v1/integrations/templates/${templateId}/publish`, {
      method: "POST",
    }),
  launchTemplate: (templateId: string, data: Record<string, unknown>) =>
    request<TemplateLaunchResponse>(`/api/v1/integrations/templates/${templateId}/launch`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // --- Outbound webhooks ---
  getWebhooks: () => request<WebhookListResponse>("/api/v1/integrations/webhooks"),
  /** The `secret` in the response is returned once, at registration, and never again. */
  createWebhook: (url: string, events?: WebhookEvent[]) =>
    request<WebhookCreatedResponse>("/api/v1/integrations/webhooks", {
      method: "POST",
      body: JSON.stringify({ url, events: events ?? [] }),
    }),
  deleteWebhook: (webhookId: string) =>
    request<{ status: string; id: string }>(`/api/v1/integrations/webhooks/${webhookId}`, {
      method: "DELETE",
    }),
  /** Recent delivery attempts — the audit trail for one customer endpoint. */
  getWebhookDeliveries: (webhookId: string) =>
    request<WebhookDeliveryListResponse>(
      `/api/v1/integrations/webhooks/${webhookId}/deliveries`
    ),

  // POST /api/v1/integrations/slack/events and /commands are intentionally
  // absent: they are Slack's receivers (signed with SLACK_SIGNING_SECRET, and
  // /commands takes form-encoded data). Nothing in the browser calls them.

  // --- Client portal (unauthenticated, white-label) ---
  // These three carry no bearer token by design — see requestPublic above.
  getPortalCampaigns: (orgSlug: string, clientId?: string) =>
    requestPublic<PortalCampaignsResponse>(
      `/api/v1/portal/${encodeURIComponent(orgSlug)}/campaigns${qs({ client_id: clientId })}`
    ),
  getPortalContent: (orgSlug: string, statusFilter?: string) =>
    requestPublic<PortalContentResponse>(
      `/api/v1/portal/${encodeURIComponent(orgSlug)}/content${qs({ status_filter: statusFilter })}`
    ),
  reviewPortalContent: (orgSlug: string, contentId: string, decision: PortalDecision) =>
    requestPublic<PortalReviewResponse>(
      `/api/v1/portal/${encodeURIComponent(orgSlug)}/content/${contentId}`,
      { method: "PATCH", body: JSON.stringify({ decision }) }
    ),

  // --- Public REST API (X-API-Key) ---
  publicMe: (apiKey: string) => requestWithApiKey<{ org_id: string }>("/api/v1/public/me", apiKey),
  publicListCampaigns: (apiKey: string) =>
    requestWithApiKey<{ items: PublicCampaignSummary[] }>("/api/v1/public/campaigns", apiKey),

  // --- Audit log ---
  getAuditLogs: (params?: AuditLogQuery) =>
    request<{ items: AuditLogEntry[] }>(`/api/v1/audit${params ? qs({ ...params }) : ""}`),

  // --- Trends ---
  /**
   * Trending topics for campaign inspiration, sourced live from Exa.
   *
   * Discriminated union on `status`: an `"unavailable"` payload has `items: never[]`
   * and a `reason`, so it cannot be rendered as trend data. Never substitute a
   * placeholder topic list for the unavailable state.
   *
   * `platform` is a plain `string` because callers pass raw select values; use
   * {@link TrendPlatform} for the supported set. An unsupported value is not an
   * error — the server answers `status: "unavailable"` naming what it accepts.
   */
  getTrends: (platform?: TrendPlatform | string) =>
    request<TrendsResponse>(`/api/v1/campaigns/trends${qs({ platform })}`),

  // --- Brand intelligence ---
  getClientIntelligence: (clientId: string) =>
    request<ClientIntelligenceResponse>(
      `/api/v1/brand-analytics/clients/${clientId}/intelligence`
    ),

  getCrossLearning: (industry?: string) =>
    request<CrossLearningResponse>(`/api/v1/brand-analytics/cross-learning${qs({ industry })}`),

  // --- Competitive intelligence ---
  /**
   * Retrieval-grounded competitor scan.
   *
   * Discriminated union on `status`. Every finding on the `"ok"` arm carries the
   * `source_url` and `retrieved_at` of the document it came from; claims that
   * could not be matched back to a retrieved source were dropped server-side and
   * counted in `dropped_unsourced_count`. Surface that count — a silently
   * shrunken finding list looks like a thin result rather than a filtered one.
   */
  runCompetitiveScan: (clientId: string, competitors?: string) =>
    request<CompetitiveScanResponse>(`/api/v1/competitive/clients/${clientId}/scan`, {
      method: "POST",
      body: JSON.stringify(competitors != null ? { competitors } : {}),
    }),

  // --- Autonomous campaigns ---
  createAutonomousCampaign: (clientId: string, goal: string) =>
    request<AutonomousCampaignResponse>("/api/v1/campaigns/autonomous", {
      method: "POST",
      body: JSON.stringify({ client_id: clientId, goal }),
    }),

  // --- Client acquisition ---
  generateOutreach: (data: OutreachRequest) =>
    request<OutreachResponse>("/api/v1/acquisition/outreach", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // --- Product analytics ---
  // POST /api/v1/events is intentionally absent from this object: lib/analytics.ts
  // posts the batch with its own `fetch(..., { keepalive: true })` so events
  // survive a page unload, which request() cannot express. It uses the exported
  // API_BASE_URL + getAuthToken above rather than duplicating auth.
  //
  // Beta metrics (docs/beta-testing-plan.md §7), scoped to the caller's org.
  getBetaMetrics: (windowDays = 28) =>
    request<BetaMetrics>(`/api/v1/beta-metrics?window_days=${windowDays}`),
};

// --- Types ---

export interface HealthResponse {
  status: string;
  service: string;
}

export interface HealthDbResponse {
  status: string;
  database: string;
}

export interface LlmTierHealth {
  provider?: string;
  model?: string;
  base_url?: string | null;
  fallbacks?: { provider: string; model: string }[];
  /** Present instead of the fields above when no provider is configured for the tier. */
  error?: string;
}

export interface LlmHealthResponse {
  order: string[];
  configured: string[];
  unconfigured: string[];
  tiers: Record<string, LlmTierHealth>;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  role: string;
  org_id: string;
}

export interface SignupRequest {
  email: string;
  password: string;
  full_name: string;
  org_name: string;
}

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

/** Mirrors `ClientUpdate` — only the fields sent are written. */
export type UpdateClientRequest = Partial<CreateClientRequest>;

/** Mirrors `BrandProfileResponse` — a client's saved brand profile. */
export interface SavedBrandProfile {
  client_id: string;
  voice_description: string | null;
  tone_attributes: Record<string, number> | null;
  vocabulary_include: string[] | null;
  vocabulary_exclude: string[] | null;
  style_rules: string[] | null;
  emoji_policy: string | null;
  competitor_differentiation: string | null;
  target_audience: string | null;
  /**
   * The one answer to "what is this client's voice?" (CF-08).
   *
   * Three stores can hold a voice — the written guide, Settings' posting-prefs
   * register, and the older `tone_attributes.register` — and each screen used to
   * read a different one, so one client showed "Friendly & casual", "Not set"
   * and "Not configured" at the same time. Render this, never a raw column.
   * Empty string when nothing is set.
   */
  effective_voice?: string;
  /** Which store `effective_voice` came from, or null when none is set. */
  voice_source?: "guide" | "register" | "tone_register" | null;
}

/** Mirrors `BrandProfileCreate` — every field has a server-side default. */
export interface BrandProfileRequest {
  voice_description?: string;
  tone_attributes?: Record<string, number>;
  vocabulary_include?: string[];
  vocabulary_exclude?: string[];
  example_posts?: Record<string, unknown>[];
  style_rules?: string[];
  emoji_policy?: string;
  competitor_differentiation?: string;
  target_audience?: string;
}

export interface BrandProfileCreatedResponse {
  status: string;
  client_id: string;
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
  budget: Record<string, unknown>;
  status: string;
  agent_plan: Record<string, unknown>;
  /**
   * Why the run failed, when it did (CF-07). Empty `{}` otherwise, and empty for
   * campaigns that failed before this was recorded — render
   * {@link campaignFailureSummary}, which says so rather than inventing a reason.
   */
  failure?: CampaignFailure | null;
  created_at: string;
}

export interface CampaignFailure {
  error?: string;
  error_type?: string;
  /**
   * The agents the crash is attributable to. Two when a parallel pair (Strategy ∥
   * SEO, Content ∥ Ad Copy) was in flight and either could have thrown — the
   * backend reports both rather than guessing.
   */
  agents?: string[];
  /** The last agent that finished, or null if none did. */
  after?: string | null;
  at?: string;
}

/** Display names for the pipeline's nodes. Mirrors AGENT_ORDER in the router. */
const AGENT_LABELS: Record<string, string> = {
  orchestrate: "Orchestrator",
  strategise: "Strategy",
  seo_research: "SEO",
  create_content: "Content",
  write_ads: "Ad Copy",
  human_review: "Human Review",
  qa_check: "QA / Brand",
  compile_output: "Compile",
  analytics: "Analytics",
};

export function agentLabel(agent: string): string {
  return AGENT_LABELS[agent] ?? agent;
}

/**
 * A one-line account of why a campaign failed, for the card and the detail page.
 *
 * Returns null when the campaign has not failed. A failed campaign with nothing
 * recorded returns a sentence saying exactly that — these are the runs that
 * failed before the reason was stored, and claiming to know more would be worse
 * than admitting the gap.
 */
export function campaignFailureSummary(campaign: Campaign): string | null {
  if (campaign.status !== "failed") return null;
  const failure = campaign.failure;
  if (!failure?.error) return "No reason was recorded for this failure.";

  const agents = failure.agents ?? [];
  let where: string;
  if (agents.length === 1) {
    where = `${agentLabel(agents[0])} failed`;
  } else if (agents.length > 1) {
    // Either branch could have thrown; say so instead of picking one.
    where = `${agents.map(agentLabel).join(" or ")} failed`;
  } else if (failure.after) {
    where = `Failed after ${agentLabel(failure.after)}`;
  } else {
    where = "The run failed";
  }
  return `${where}: ${failure.error}`;
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
  languages?: string[];
}

export type ReviewDecision = "approved" | "revise_content" | "revise_ads";

export interface ReviewSubmittedResponse {
  status: string;
  decision: string;
}

/** The ad platforms the Ad Copy agent writes for. */
export type AdPlatform = "google" | "meta" | "linkedin";

/**
 * One ad variant in the shape its network renders, from
 * `backend/services/ad_variants.py`. Which keys of `fields` are present depends
 * on `platform`: Google has `headlines`/`descriptions`, Meta has
 * `primary_text`/`headline`/`description`, LinkedIn has
 * `intro_text`/`headline`/`description`.
 *
 * Read this rather than `body` when rendering an ad — `body` is the same copy
 * flattened to labelled text for the generic paths.
 */
export interface AdVariant {
  platform: AdPlatform;
  variant: number;
  angle: string;
  cta: string;
  target_keyword: string;
  notes: string;
  fields: {
    headlines?: string[];
    descriptions?: string[];
    primary_text?: string;
    intro_text?: string;
    headline?: string;
    description?: string;
  };
  /** Per-field character limits for this network, for the over-limit hint. */
  limits: Record<string, number>;
  /** Required fields that came back empty. */
  missing: string[];
  /** True when nothing usable was generated. Such a variant is stored failed. */
  is_empty: boolean;
}

/** `content_piece.metadata`, as the API spells it (`metadata_`). */
export interface ContentMetadata {
  /** Present on ad variants. */
  ad?: AdVariant;
  /** Why a piece is not a usable draft, set when generation fell short. */
  generation?: {
    status: "failed" | "incomplete";
    reason?: string;
    missing?: string[];
  };
  post_url?: string | null;
  publish_error?: string | null;
  /**
   * Why a scheduled post could not go out, when the cause is the workspace
   * rather than the post (CF-01) — today, no connected account for its platform.
   * The post is returned to Approved with its schedule cleared, not marked
   * Failed, and this is cleared when it publishes or is rescheduled.
   */
  publish_blocked?: {
    reason: string;
    code?: string;
    platform?: string;
    at?: string;
  } | null;
  [key: string]: unknown;
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
  metadata_?: ContentMetadata | null;
}

/** The structured ad on a piece, or null when it is not an ad variant. */
export function adVariantOf(piece: Pick<ContentPiece, "metadata_">): AdVariant | null {
  const ad = piece.metadata_?.ad;
  return ad && typeof ad === "object" && ad.fields ? ad : null;
}

/**
 * Why this piece cannot be approved, or null when it can.
 *
 * An ad variant the agent returned empty is stored failed rather than draft, but
 * older rows predate that and are still drafts with nothing in them — so this
 * checks the content, not only the status (CF-05).
 */
export function unusableReason(piece: Pick<ContentPiece, "metadata_" | "body">): string | null {
  const generation = piece.metadata_?.generation;
  if (generation?.status === "failed") {
    return generation.reason ?? "This item was generated empty.";
  }
  const ad = adVariantOf(piece);
  if (ad?.is_empty) return "The ad copy agent returned no usable copy for this variant.";
  if (!ad && !piece.body.trim()) return "This item has no content.";
  return null;
}

export interface ContentListResponse {
  items: ContentPiece[];
  total: number;
  page: number;
  per_page: number;
}

/** Query params accepted by `GET /api/v1/content`. Note `content_status`, not `status`. */
export interface ContentQuery {
  campaign_id?: string;
  client_id?: string;
  content_status?: string;
  platform?: string;
  page?: number;
  per_page?: number;
}

/** Mirrors `ContentUpdateRequest` — only these four fields are writable. */
export interface ContentUpdateRequest {
  title?: string;
  body?: string;
  hashtags?: string[];
  status?: string;
}

export interface ContentApprovedResponse {
  status: string;
  content_id: string;
}

export interface ContentSuggestion {
  original_id: string;
  platform: string;
  title: string;
  body: string;
  performance_score: number | null;
  reason: string;
}

export interface RepurposeResponse {
  status: string;
  platforms: string[];
  count: number;
}

export interface VariantsResponse {
  status: string;
  variant_group: string;
  /** Variant labels created, e.g. ["B", "C"]. The original piece becomes "A". */
  variants: string[];
}

export interface GeneratedImageResponse {
  /** "generated" | "skipped" (no FAL_API_KEY) | "error". */
  status: string;
  image_url: string | null;
  platform?: string;
  message?: string;
}

// --- Content analytics (honest-data contract) ---

export type AnalyticsMetricField =
  | "impressions"
  | "reach"
  | "engagement"
  | "clicks"
  | "shares"
  | "likes";

/**
 * One daily snapshot for a content piece.
 *
 * DATA RELIABILITY — read this before rendering any number here.
 * Every metric is `number | null`:
 *   * `null` = the platform did not expose this metric. It was never measured.
 *   * `0`    = the platform reported a measured zero.
 *
 * `?? 0` (or `|| 0`) on any of these fields is FORBIDDEN: it converts "we could
 * not measure this" into "we measured zero", which is a fabricated metric. The
 * backend goes out of its way to write a real SQL NULL (`analytics_fetcher.py`
 * uses `null()` to defeat the column DEFAULT 0) precisely so the distinction
 * survives to this type. Render an explicit "not available" instead, and use
 * `measured` / `not_available` to decide which fields to show at all.
 */
export interface AnalyticsSnapshot {
  date: string;
  impressions: number | null;
  reach: number | null;
  engagement: number | null;
  clicks: number | null;
  shares: number | null;
  likes: number | null;
  /** Fields the platform actually returned for this snapshot. */
  measured: AnalyticsMetricField[];
  /** Fields the platform did not return. Show these as unavailable, not zero. */
  not_available: AnalyticsMetricField[];
  source: string | null;
  fetched_at: string | null;
}

export type ContentAnalyticsStatus =
  | "ok"
  | "skipped"
  | "unavailable"
  | "error"
  | "not_refreshed";

interface ContentAnalyticsBase {
  content_id: string;
  platform: string;
  /** Most recent stored snapshot, or null when nothing was ever measured. */
  latest: AnalyticsSnapshot | null;
  /** Stored history, newest first. Present on every status — see the per-arm docs. */
  items: AnalyticsSnapshot[];
}

/**
 * `GET /api/v1/content/{id}/analytics`.
 *
 * `status` describes the **live refresh attempt**, not the stored history:
 *   * `ok`            — fresh metrics were fetched and recorded today.
 *   * `skipped`       — already refreshed today; `items` is still current.
 *   * `unavailable`   — nothing could be fetched and NOTHING was persisted.
 *                       `reason` says why. Do not present `items` as fresh.
 *   * `error`         — the piece is missing or not published.
 *   * `not_refreshed` — `?refresh=false`, or the piece is not published, so no
 *                       fetch was attempted at all.
 *
 * The failure arms type `reason` as a non-null `string`, so narrowing on
 * `status` guarantees there is something to show the user.
 */
export type ContentAnalyticsResponse =
  | (ContentAnalyticsBase & { status: "ok"; reason: null })
  | (ContentAnalyticsBase & { status: "skipped"; reason: string })
  | (ContentAnalyticsBase & { status: "unavailable"; reason: string })
  | (ContentAnalyticsBase & { status: "error"; reason: string })
  | (ContentAnalyticsBase & { status: "not_refreshed"; reason: null });

export interface VideoScriptRequest {
  format: string;
  topic: string;
  client_id?: string;
  target_audience?: string;
}

export interface VideoScriptSegment {
  timestamp?: string;
  type?: string;
  narration?: string;
  visual_cue?: string;
  audio_cue?: string;
}

export interface VideoScriptResponse {
  title: string;
  format: string;
  duration?: string;
  segments: VideoScriptSegment[];
  hashtags?: string[];
  thumbnail_idea?: string;
  /** Present only when the model output was not parseable JSON. */
  raw_script?: string;
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

export interface CampaignProgress {
  campaign_status: string;
  progress: number;
  agent_statuses: Record<string, string>;
  is_active: boolean;
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
  published_at?: string | null;
}

export type CalendarApiResponse = CalendarEntry[] | { items: CalendarEntry[] };

export interface ScheduledResponse {
  status: string;
  scheduled_at: string;
}

export interface PublishedResponse {
  status: string;
  content_id: string;
  post_id: string | null;
  url: string | null;
}

export interface Plan {
  tier: string;
  price_id?: string;
  clients_limit?: number;
  posts_limit?: number;
  campaigns_limit?: number;
  features?: string[];
  amount?: number;
}

export interface SubscriptionInfo {
  plan_tier: string;
  status?: string;
  clients_limit?: number;
  posts_limit?: number;
  posts_used?: number;
  campaigns_limit?: number;
  price_id?: string;
  amount?: number;
  features?: string[];
}

export interface CheckoutResponse {
  checkout_url: string;
  session_id?: string;
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

/**
 * The invite flow still returns a temporary password because no signed
 * invite-link flow exists yet (see the TODOs in `routers/team.py`). Treat
 * `temp_password` as a credential: show it once, never log it.
 */
export interface TeamInviteResponse {
  status: string;
  /** Whether an invitation email actually went out. Authoritative — do not
   * infer it from `message`, which is display copy and may be reworded. */
  email_sent: boolean;
  message: string;
  email: string;
  role: string;
  temp_password: string;
  user_id: string;
}

export interface TeamMemberRoleResponse {
  status: string;
  role?: string;
  user_id?: string;
}

// --- Reports ---

export type ReportPeriod = "weekly" | "monthly" | "quarterly";

export interface ReportPeriodOption {
  period: ReportPeriod;
  label: string;
}

export interface ClientReport {
  client_name: string;
  industry: string | null;
  period: string;
  start_date: string;
  end_date: string;
  metrics: {
    total_campaigns: number;
    total_content_pieces: number;
    published: number;
    drafts: number;
    approved: number;
  };
  platform_breakdown: Record<string, number>;
  status_breakdown: Record<string, number>;
}

// --- Organization settings / integrations ---

export interface OrgSettings {
  name: string;
  domain: string | null;
  settings: Record<string, unknown>;
}

export interface OrgSettingsUpdate {
  name?: string;
  domain?: string;
  /** Shallow-merged into the existing settings object server-side. */
  settings?: Record<string, unknown>;
}

export interface OrgSettingsUpdatedResponse extends OrgSettings {
  status: string;
}

export interface ApiKeySummary {
  id: string;
  name: string;
  prefix: string;
  permissions: string[];
  last_used_at: string | null;
  created_at: string | null;
}

export interface ApiKeyCreatedResponse {
  id: string;
  name: string;
  /** Plaintext key — returned exactly once, at creation. */
  key: string;
  prefix: string;
  permissions: string[];
}

export interface PlatformAccountSummary {
  id: string;
  platform: string;
  account_handle: string | null;
  display_name: string | null;
  status: string;
  followers_count: number | null;
}

export interface WhiteLabelBranding {
  id: string;
  custom_domain: string | null;
  logo_url: string | null;
  primary_color: string | null;
  company_name: string | null;
  support_email: string | null;
  portal_enabled: boolean;
  email_from_name: string | null;
  is_active: boolean;
}

/** `{ is_active: false }` is returned when no branding row exists yet. */
export type WhiteLabelResponse = WhiteLabelBranding | { is_active: false };

export interface WhiteLabelUpdate {
  custom_domain?: string;
  logo_url?: string;
  primary_color?: string;
  company_name?: string;
  support_email?: string;
  portal_enabled?: boolean;
  email_from_name?: string;
  is_active?: boolean;
}

// --- OAuth ---

export interface OAuthAuthorizeResponse {
  authorize_url: string;
  platform: string;
}

export interface OAuthCallbackRequest {
  code: string;
  /** Required: the CampaignForge client the account is attached to. */
  client_id: string;
  account_handle?: string;
  display_name?: string;
}

export interface OAuthCallbackResponse {
  status: string;
  platform: string;
  account_handle: string;
}

export interface OAuthDisconnectResponse {
  status: string;
  platform: string;
}

// --- Comments / notifications ---

export interface ContentCommentItem {
  id: string;
  content_id: string;
  user_id: string;
  user_name: string;
  body: string;
  created_at: string | null;
}

export interface NotificationItem {
  id: string;
  type: string;
  title: string;
  body: string;
  data: Record<string, unknown>;
  read: boolean;
  created_at: string | null;
}

// --- Campaign templates ---

/**
 * The one campaign-template taxonomy (CF-14).
 *
 * The filter tabs listed launch / social / awareness / seasonal /
 * thought-leadership while the seeded rows were categorised recurring / b2b /
 * events, so "Social" and "Thought Leadership" returned nothing and three
 * categories had no tab at all. Both ends read this list now — a card's label
 * and the tab that finds it cannot diverge again.
 *
 * Mirrors `db/seed.sql`; a new category goes here and there together.
 */
export const TEMPLATE_CATEGORIES = [
  { id: "launch", label: "Launch" },
  { id: "social", label: "Social" },
  { id: "awareness", label: "Awareness" },
  { id: "thought-leadership", label: "Thought Leadership" },
  { id: "seasonal", label: "Seasonal" },
  { id: "events", label: "Events" },
] as const;

export type TemplateCategory = (typeof TEMPLATE_CATEGORIES)[number]["id"];

/** A category's display name. An unknown one is title-cased, never dropped. */
export function templateCategoryLabel(category: string): string {
  const known = TEMPLATE_CATEGORIES.find((c) => c.id === category);
  if (known) return known.label;
  return category
    .replace(/-/g, " ")
    .replace(/\b\w/g, (l) => l.toUpperCase());
}

export interface CampaignTemplateSummary {
  id: string;
  name: string;
  description: string;
  category: string;
  objective_template: string;
  channels: string[];
  uses_count: number;
  is_public: boolean;
}

/** The marketplace listing omits `objective_template` and `is_public`. */
export interface MarketplaceTemplateSummary {
  id: string;
  name: string;
  description: string;
  category: string;
  channels: string[];
  uses_count: number;
}

export interface CampaignTemplateDetail extends CampaignTemplateSummary {
  content_directives: Record<string, unknown>;
}

export interface CampaignTemplateCreate {
  name: string;
  description?: string;
  category?: string;
  objective_template?: string;
  channels?: string[];
  content_directives?: Record<string, unknown>;
}

export interface TemplateMutationResponse {
  /** "created" | "forked" | "published". */
  status: string;
  id: string;
}

export interface TemplateLaunchResponse {
  status: string;
  prefill: {
    campaign_name: string;
    objective: string;
    channels: string[];
    content_directives: Record<string, unknown>;
  };
}

// --- Outbound webhooks ---

/** Mirrors `SUPPORTED_EVENTS` in services/webhook_dispatcher.py. */
export type WebhookEvent = "campaign.completed" | "content.approved";

export interface Webhook {
  id: string;
  org_id: string;
  url: string;
  events: WebhookEvent[];
  is_active: boolean;
  created_at: string | null;
}

/** Registration response — the only place the signing secret is ever shown. */
export interface WebhookCreatedResponse extends Webhook {
  secret: string;
}

export interface WebhookListResponse {
  items: Webhook[];
  total: number;
}

export interface WebhookDelivery {
  id: string;
  webhook_id: string;
  event_type: string;
  attempt: number;
  status: string;
  response_code: number | null;
  error: string | null;
  created_at: string | null;
}

export interface WebhookDeliveryListResponse {
  items: WebhookDelivery[];
  total: number;
}

// --- Client portal (unauthenticated) ---

export interface PortalBranding {
  company_name: string | null;
  logo_url: string | null;
  primary_color: string | null;
}

export interface PortalCampaign {
  id: string;
  name: string;
  status: string;
  channels: string[];
  start_date: string | null;
  end_date: string | null;
}

export interface PortalCampaignsResponse {
  branding: PortalBranding;
  items: PortalCampaign[];
}

export interface PortalContentItem {
  id: string;
  platform: string;
  title: string;
  body: string;
  status: string;
  created_at: string | null;
}

export interface PortalContentResponse {
  items: PortalContentItem[];
}

export type PortalDecision = "approve" | "reject";

export interface PortalReviewResponse {
  status: string;
  content_id: string;
}

// --- Public REST API ---

export interface PublicCampaignSummary {
  id: string;
  name: string;
  status: string;
  channels: string[];
  start_date: string | null;
  end_date: string | null;
}

// --- Audit log ---

export interface AuditLogQuery {
  resource_type?: string;
  action?: string;
  limit?: number;
}

export interface AuditLogEntry {
  id: string;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  details: Record<string, unknown> | null;
  user_id: string | null;
  ip_address: string | null;
  created_at: string | null;
}

// --- Trends (honest-data contract) ---

/** Mirrors `SUPPORTED_PLATFORMS` in services/trends.py. */
export type TrendPlatform = "twitter" | "linkedin" | "instagram" | "facebook";

export interface TrendItem {
  topic: string;
  /** Verifiable source URL. Every item has one — this is not a synthesised list. */
  url: string;
  source: string | null;
  platform: string | null;
  published_date: string | null;
  /** Days since publication. A recency signal — NOT search volume. */
  recency_days: number | null;
  relevance_score: number | null;
  provenance: "exa_search";
}

/**
 * `GET /api/v1/campaigns/trends`.
 *
 * Exa is a web-search API: it reports no search volume and no marketing
 * category, so those fields are absent and named in `fields_not_provided`.
 * Do not invent them.
 *
 * The `"unavailable"` arm types `items` as `never[]`, so reading a topic off an
 * unavailable payload is a compile error rather than an empty-state bug. Render
 * `reason` instead — never a sample or placeholder topic list.
 */
export type TrendsResponse =
  | {
      status: "ok";
      source: "exa_search";
      platform: string | null;
      /** The exact query sent to Exa, surfaced for auditability. */
      query: string;
      fetched_at: string;
      /** Fields Exa cannot supply, e.g. ["volume", "category"]. */
      fields_not_provided: string[];
      provenance: string;
      items: TrendItem[];
    }
  | {
      status: "unavailable";
      reason: string;
      items: never[];
      platform?: string | null;
      query?: string;
      http_status?: number;
    };

// --- Brand intelligence / cross-learning ---

export interface ClientIntelligenceTopContent {
  id: string;
  platform: string;
  title: string;
  performance_score: number | null;
}

export interface ClientIntelligenceResponse {
  client_name: string;
  industry: string | null;
  campaign_count: number;
  platform_breakdown: Record<string, number>;
  status_breakdown: Record<string, number>;
  top_content: ClientIntelligenceTopContent[];
  brand_voice: {
    voice_description: string;
    tone_attributes: Record<string, number>;
    target_audience: string;
  };
}

export interface CrossLearningInsight {
  platform: string;
  avg_performance: number;
  content_count: number;
  insight: string;
}

export interface IndustryBenchmarks {
  industry: string;
  status?: "available" | "unavailable";
  /** Present when `status` is "unavailable". Render it verbatim — it explains
   *  whether the gap is missing data or the cross-org privacy floor, and the
   *  two need different responses from the user. */
  reason?: string;
  avg_impressions: number | null;
  avg_engagement: number | null;
  avg_clicks: number | null;
  avg_likes: number | null;
  /** Number of snapshots behind the averages. Zero means there is no benchmark. */
  sample_size: number;
  /** Distinct organisations contributing. Benchmarks are suppressed below the
   *  server's minimum, so this is 0 whenever `status` is "unavailable". */
  contributing_orgs?: number;
}

export interface CrossLearningResponse {
  insights: CrossLearningInsight[];
  /** Null unless an `industry` filter was passed. */
  benchmarks: IndustryBenchmarks | null;
}

// --- Competitive intelligence (honest-data contract) ---

export type CompetitiveFindingCategory =
  | "messaging_theme"
  | "content_gap"
  | "positioning"
  | "offer"
  | "channel"
  | "launch"
  | "observation";

export interface CompetitiveSource {
  id: string;
  competitor: string;
  title: string;
  url: string;
  domain: string | null;
  published_date: string | null;
  retrieved_at: string;
  excerpt: string | null;
}

/**
 * One sourced finding. `source_url` is copied from the retrieved document, never
 * from the model, and `published_date` is null when the publisher did not supply
 * one — do not backfill it with `retrieved_at`.
 */
export interface CompetitiveFinding {
  competitor: string;
  category: CompetitiveFindingCategory;
  claim: string;
  evidence: string | null;
  source_id: string;
  source_url: string;
  source_title: string;
  source_domain: string | null;
  published_date: string | null;
  retrieved_at: string;
}

export interface CompetitiveDroppedClaim {
  claim: string;
  claimed_source_url: string | null;
}

export interface CompetitiveCounterCampaign {
  name: string;
  objective: string | null;
  channels: string[];
  key_message: string | null;
  based_on_urls: string[];
}

/** Agency advice derived from the cited findings — recommendations, not facts. */
export interface CompetitiveRecommendations {
  counter_campaigns: CompetitiveCounterCampaign[];
  strategy: string | null;
  note: string;
}

interface CompetitiveScanBase {
  client_id: string;
  client_name: string;
}

/**
 * `POST /api/v1/competitive/clients/{id}/scan`.
 *
 * The `"unavailable"` arm has `findings: never[]` and no `recommendations`, so a
 * consumer cannot read intelligence off a failed scan. It reaches that state
 * when Exa is unconfigured, no competitor name could be parsed, no source was
 * retrieved, the model failed, or every claim was dropped as unsourced.
 */
export type CompetitiveScanResponse =
  | (CompetitiveScanBase & {
      status: "ok";
      source: "exa_search";
      retrieved_at: string;
      competitors: string[];
      /** competitor name → the exact query sent to Exa. */
      queries: Record<string, string>;
      sources: CompetitiveSource[];
      findings: CompetitiveFinding[];
      /** Model claims dropped because they matched no retrieved source. Show it. */
      dropped_unsourced_count: number;
      dropped_unsourced: CompetitiveDroppedClaim[];
      recommendations: CompetitiveRecommendations;
      retrieval_errors: string[];
      /** e.g. ["traffic", "ad_spend", "share_of_voice", ...] — never estimate these. */
      fields_not_provided: string[];
      provenance: string;
    })
  | (CompetitiveScanBase & {
      status: "unavailable";
      reason: string;
      findings: never[];
      competitors?: string[];
      queries?: Record<string, string>;
      sources?: CompetitiveSource[];
      dropped_unsourced_count?: number;
      dropped_unsourced?: CompetitiveDroppedClaim[];
      retrieval_errors?: string[];
      http_status?: number;
    });

// --- Knowledge base / RAG ---
//
// No `/api/v1` route returns this today: `services/knowledge_base.py` is called
// server-side by the Strategy agent only, so there is no client method for it.
// The envelope is typed here so any Phase-3 surface that exposes retrieval
// carries the disclosure rather than inventing a shape. `retrieval_mode` is the
// disclosure: "keyword" means the semantic index was unavailable (see `reason`)
// and results are word-overlap matches — it must never be presented as semantic
// search.

export type RetrievalMode = "vector" | "keyword";

export interface KnowledgeResult {
  title: string;
  content: string;
  retrieval_mode?: RetrievalMode;
  score?: number;
  source?: string;
}

export interface KnowledgeRetrievalPayload {
  retrieval_mode: RetrievalMode;
  /** Why this mode was used. Always populated when mode is "keyword". */
  reason: string;
  provider: string;
  model: string;
  count: number;
  results: KnowledgeResult[];
}

// --- Autonomous campaigns / acquisition ---

export interface AutonomousCampaignResponse {
  id: string;
  name: string;
  status: string;
  plan: Record<string, unknown>;
}

export interface OutreachRequest {
  prospect_name: string;
  industry: string;
  pain_points: string[];
}

export interface OutreachEmail {
  subject: string;
  body: string;
  send_day: number;
}

export interface OutreachResponse {
  emails: OutreachEmail[];
  /** Present only when the model output was not parseable JSON. */
  raw_response?: string;
}

// --- Beta metrics ---

export interface BetaMetrics {
  window_days: number;
  since: string;
  scope: string;
  time_to_first_campaign: {
    users_with_campaign: number;
    median_seconds: number | null;
    p90_seconds: number | null;
    target_seconds: number;
  };
  campaign_outcomes: {
    created: number;
    completed: number;
    failed: number;
    in_flight: number;
    completion_rate: number | null;
    failure_rate: number | null;
    completion_target: number;
    failure_target: number;
  };
  agent_step_dropoff: {
    agent: string;
    campaigns_reached: number;
    share_of_started: number | null;
    dropped_from_previous: number;
  }[];
  feature_adoption: { feature: string; users: number; uses: number }[];
  session_duration: {
    sessions: number;
    median_seconds: number | null;
    mean_seconds: number | null;
  };
  return_rate: {
    day: number;
    eligible_users: number;
    returned_users: number;
    rate: number | null;
  }[];
  errors_by_endpoint: {
    endpoint: string;
    method: string;
    errors: number;
    server_errors: number;
  }[];
  request_rates: {
    note: string;
    total_requests: number;
    total_errors: number;
    error_rate: number | null;
    by_endpoint: {
      endpoint: string;
      method: string;
      requests: number;
      errors: number;
      error_rate: number;
    }[];
  };
}

// --- Posts queue (phase 3) ---
// Kept in one block so the phase branches merge cleanly. Contract for approve,
// schedule and publish: docs/cadence-port-plan-260921.md §4.

/** The DB value behind each Queue tab. `draft` is labelled Pending in the UI. */
export type QueueStatus = "draft" | "approved" | "scheduled" | "published" | "failed";

/**
 * A row from `GET /api/v1/content`. The list endpoint serialises the ORM row,
 * so it carries more than {@link ContentPiece}; these extras are optional
 * because the single-item endpoints do not return them.
 */
export interface QueuePost extends ContentPiece {
  scheduled_at?: string | null;
  published_at?: string | null;
}

export interface QueueListResponse {
  items: QueuePost[];
  total: number;
  page: number;
  per_page: number;
}

export interface ModerationIssue {
  severity: string;
  message: string;
}

export interface ApproveResult {
  id: string;
  status: "approved";
  moderation?: {
    status: "passed" | "unavailable" | "overridden";
    issues: ModerationIssue[];
  };
}

/** `detail.code` of a structured API error, or null. */
export function apiErrorCode(err: unknown): string | null {
  if (!(err instanceof ApiError)) return null;
  const d = err.detail as { code?: unknown } | null;
  return d && typeof d === "object" && typeof d.code === "string" ? d.code : null;
}

/**
 * `detail.message` of a structured API error, or null.
 *
 * The server words these for the reader — a plan limit says which plan, what the
 * limit is and what to do about it — so showing it beats re-inventing the
 * sentence on each screen.
 */
export function apiErrorMessage(err: unknown): string | null {
  if (!(err instanceof ApiError)) return null;
  const d = err.detail as { message?: unknown } | null;
  return d && typeof d === "object" && typeof d.message === "string" ? d.message : null;
}

/** Issues carried by a `409 moderation_flagged`; empty for anything else. */
export function moderationIssues(err: unknown): ModerationIssue[] {
  if (apiErrorCode(err) !== "moderation_flagged") return [];
  const issues = ((err as ApiError).detail as { issues?: unknown }).issues;
  return Array.isArray(issues) ? (issues as ModerationIssue[]) : [];
}

export const postsApi = {
  /** Note the filter param is `content_status` — `status` is silently ignored. */
  list: (params: {
    content_status: QueueStatus;
    client_id?: string;
    platform?: string;
    page?: number;
    per_page?: number;
  }) => request<QueueListResponse>(`/api/v1/content${qs(params)}`),

  /** Total for one status under the same filters — one row fetched, `total` read. */
  count: async (status: QueueStatus, filters: { client_id?: string; platform?: string }) => {
    const res = await request<QueueListResponse>(
      `/api/v1/content${qs({ ...filters, content_status: status, per_page: 1 })}`
    );
    return res.total;
  },

  /** Runs moderation first. 409 `moderation_flagged` unless `override`. */
  approve: (id: string, override = false) =>
    request<ApproveResult>(`/api/v1/content/${id}/approve${override ? "?override=true" : ""}`, {
      method: "POST",
    }),

  /**
   * Send a post whose publish failed back to `approved`, ready to try again.
   *
   * Moderation runs again — a failed post can be edited, so the text may not be
   * the text that was approved. 409 `not_failed` if it is not a failed post.
   */
  retry: (id: string, override = false) =>
    request<ApproveResult>(`/api/v1/content/${id}/retry${override ? "?override=true" : ""}`, {
      method: "POST",
    }),

  edit: (id: string, data: { title?: string; body?: string; hashtags?: string[] }) =>
    request<ContentPiece>(`/api/v1/content/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
};

// --- Amplify (phase 4) ---
// One source → up to 8 angle-distinct drafts. Preview saves nothing to the
// queue; commit writes the kept atoms as `draft` (Pending). Backend:
// backend/src/agency/routers/amplify.py.

/** Closed angle taxonomy — mirrors REPURPOSE_ANGLES in services/repurpose.py. */
export const AMPLIFY_ANGLES = [
  "hook",
  "how-to",
  "contrarian",
  "story",
  "data-point",
  "question",
  "behind-the-scenes",
  "listicle",
] as const;
export type AmplifyAngle = (typeof AMPLIFY_ANGLES)[number];
export const AMPLIFY_MAX_ATOMS = AMPLIFY_ANGLES.length;

/** Platforms the Amplify endpoint accepts (PLATFORM_CHAR_LIMITS keys). */
export const AMPLIFY_PLATFORMS = [
  { id: "twitter", label: "X / Twitter" },
  { id: "linkedin", label: "LinkedIn" },
  { id: "instagram", label: "Instagram" },
  { id: "facebook", label: "Facebook" },
  { id: "tiktok", label: "TikTok" },
] as const;

// Declaration merge: `/billing/subscription` also reports the Amplify quota.
export interface SubscriptionInfo {
  generations_used?: number;
  generations_limit?: number;
}

export interface AmplifyAtom {
  platform: string;
  angle: AmplifyAngle;
  title: string;
  body: string;
  hashtags: string[];
  /** Overlaps a recent post of this client, or an earlier atom in the pack. A warning, not a block. */
  duplicate_warning: boolean;
  /** Published length (body + appended hashtags) and the platform's hard cap. */
  char_count: number;
  char_limit: number;
}

export interface AmplifyPreviewRequest {
  client_id: string;
  source_content_id?: string;
  /** A saved Create-screen asset (blog post, comparison page, niche scan, video script, launch kit). */
  source_asset_id?: string;
  source_text?: string;
  platforms: string[];
  max_atoms?: number;
}

export interface AmplifyPreviewResponse {
  pack_id: string;
  atoms: AmplifyAtom[];
  /** How many atoms were asked of the model, and how many it returned unusably. */
  requested: number;
  dropped: number;
}

export type AmplifyCommitAtom = Pick<AmplifyAtom, "platform" | "angle" | "title" | "body" | "hashtags">;

export interface AmplifyCommitResponse {
  created: string[];
  count: number;
}

export interface AmplifyPack {
  id: string;
  client_id: string;
  client_name: string | null;
  source_content_id: string | null;
  source_asset_id?: string | null;
  source_title: string | null;
  source_excerpt: string | null;
  platforms: string[];
  atom_count: number;
  committed_count: number;
  created_at: string | null;
}

/** HTTP status of a failed api call, when it has one. */
export function apiErrorStatus(err: unknown): number | null {
  return err instanceof ApiError ? err.status : null;
}

/** 402 from preview: the org's Amplify generations for this period are used up. */
export function isGenerationQuotaError(err: unknown): boolean {
  return apiErrorStatus(err) === 402;
}

export const amplifyApi = {
  preview: (data: AmplifyPreviewRequest, signal?: AbortSignal) =>
    request<AmplifyPreviewResponse>("/api/v1/amplify/preview", {
      method: "POST",
      body: JSON.stringify(data),
      signal,
    }),
  commit: (packId: string, atoms: AmplifyCommitAtom[]) =>
    request<AmplifyCommitResponse>(`/api/v1/amplify/${packId}/commit`, {
      method: "POST",
      body: JSON.stringify({ atoms }),
    }),
  packs: (clientId?: string) => request<{ items: AmplifyPack[] }>(`/api/v1/amplify/packs${qs({ client_id: clientId })}`),
  /** One pack, with the drafts it queued and a per-platform breakdown (CF-15). */
  pack: (packId: string) => request<AmplifyPackDetail>(`/api/v1/amplify/packs/${packId}`),
};

/**
 * What became of one platform in a pack.
 *
 * `not_kept` and `not_generated` are distinguishable only from the pack's
 * counts, because atoms are never persisted — `commit` writes the kept ones to
 * `content_piece` and the rest are gone. Where the counts cannot tell them
 * apart, the backend says `not_kept` and `dropped_count` gives the UI enough to
 * word it honestly.
 */
export type AmplifyPlatformStatus = "queued" | "not_kept" | "not_generated";

export interface AmplifyPackPost {
  id: string;
  platform: string;
  angle: string | null;
  status: string;
  title: string;
  excerpt: string | null;
}

export interface AmplifyPackDetail {
  id: string;
  client_id: string;
  platforms: string[];
  atom_count: number;
  committed_count: number;
  created_at: string | null;
  posts: AmplifyPackPost[];
  platform_breakdown: { platform: string; status: AmplifyPlatformStatus }[];
  dropped_count: number;
  unqueued_platforms: string[];
}
