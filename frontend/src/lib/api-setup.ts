/*
 * Setup › Profile and Setup › Accounts (Cadence's IntakeScreen + ConnectScreen).
 * Backend: routers/setup.py, plus the existing /magic-brief scan and /oauth flow.
 */
import { api, qs, request, type BrandProfile } from "@/lib/api";
import type { CreativeAsset } from "@/lib/api-foundation";

export const TONE_REGISTERS = ["Blunt & technical", "Friendly & casual", "Bold & punchy", "Calm & authoritative"] as const;
export type ToneRegister = (typeof TONE_REGISTERS)[number];

export interface IntakeAnswers {
  audience: string;
  differentiator: string;
  tone: string;
}

export interface BrandVoiceGuide {
  voice_description: string;
  vocabulary_include: string[];
  vocabulary_exclude: string[];
  example_sentence: string;
}

export interface SetupProfile {
  client_id: string;
  brand_name: string;
  website_url: string | null;
  /** A brand_profile row exists for this client. */
  approved: boolean;
  answers: IntakeAnswers;
  /** null until any voice description or vocabulary is on file. */
  brand_voice: BrandVoiceGuide | null;
  campaign_focus: string | null;
  updated_at: string | null;
}

export interface AnswerCoaching {
  /** false when the check itself failed — the answer is kept, never blocked. */
  available: boolean;
  is_thin: boolean;
  coaching_note: string;
}

export interface StrategyLens {
  framework: string;
  origin: string;
  critique: string;
  suggestion: string;
}

export interface StrategyLensPayload {
  lenses: StrategyLens[];
  tension: string;
  synthesis: string;
}

export interface ClientAccount {
  id: string;
  platform: string;
  account_handle: string | null;
  display_name: string | null;
  /**
   * `connected` — real OAuth tokens, the product publishes to it.
   * `manual` — a page the operator registered themselves; there are no tokens and
   * nothing publishes to it. Never render a manual channel as "Connected".
   */
  status: string;
  /** Public address of the page. Manual channels only, and optional even there. */
  profile_url: string | null;
  connected_at: string | null;
}

/** Channels a page can be registered for by hand (`MANUAL_PLATFORMS` in routers/setup.py). */
export const MANUAL_PLATFORMS = [
  "twitter",
  "linkedin",
  "facebook",
  "instagram",
  "tiktok",
  "youtube",
  "reddit",
  "threads",
  "bluesky",
] as const;

export interface ManualAccountInput {
  platform: string;
  account_handle: string;
  profile_url?: string | null;
  display_name?: string | null;
}

export interface OAuthPlatformStatus {
  configured: boolean;
  scopes: string[];
}

export interface ClientAccountsResponse {
  accounts: ClientAccount[];
  oauth: Record<string, OAuthPlatformStatus>;
}

const base = (clientId: string) => `/api/v1/setup/${clientId}`;

export const setupApi = {
  /** The website read — the existing Magic Brief (SSRF-guarded server-side fetch + worker LLM). */
  scanWebsite: (url: string, signal?: AbortSignal) =>
    request<BrandProfile>("/api/v1/magic-brief", { method: "POST", body: JSON.stringify({ url }), signal }),

  getProfile: (clientId: string) => request<SetupProfile>(`${base(clientId)}/profile`),
  approveProfile: (clientId: string, data: { url?: string | null } & IntakeAnswers) =>
    request<SetupProfile>(`${base(clientId)}/profile`, { method: "PUT", body: JSON.stringify(data) }),
  evaluateAnswer: (clientId: string, questionId: "audience" | "differentiator", answer: string, signal?: AbortSignal) =>
    request<AnswerCoaching>(`${base(clientId)}/profile/evaluate-answer`, {
      method: "POST",
      body: JSON.stringify({ question_id: questionId, answer }),
      signal,
    }),

  draftBrandVoice: (clientId: string, signal?: AbortSignal) =>
    request<BrandVoiceGuide>(`${base(clientId)}/brand-voice/generate`, { method: "POST", signal }),
  approveBrandVoice: (clientId: string, guide: BrandVoiceGuide) =>
    request<SetupProfile>(`${base(clientId)}/brand-voice`, { method: "PUT", body: JSON.stringify(guide) }),

  runStrategyLens: (clientId: string, signal?: AbortSignal) =>
    request<CreativeAsset<StrategyLensPayload>>(`${base(clientId)}/strategy-lens`, { method: "POST", signal }),

  listAccounts: (clientId: string) => request<ClientAccountsResponse>(`${base(clientId)}/accounts`),
  authorizeUrl: (platform: string, clientId: string, codeChallenge?: string) =>
    request<{ authorize_url: string; platform: string }>(
      `/api/v1/oauth/${platform}/authorize${qs({ client_id: clientId, code_challenge: codeChallenge })}`
    ),
  completeOAuth: (
    platform: string,
    data: { code: string; client_id: string; state: string; code_verifier?: string }
  ) =>
    request<{ status: string; platform: string; account_handle: string }>(`/api/v1/oauth/${platform}/callback`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  disconnect: (platform: string, accountId: string) => api.disconnectPlatformAccount(platform, accountId),

  /*
   * Manual channels — a page the operator already manages, registered with no
   * OAuth. The backend writes `status: "manual"` and no tokens whatever we send,
   * so nothing here can accidentally create something a publisher would pick up.
   * Gated on `oauth.connect` like the OAuth routes, so a member or viewer gets 403.
   */
  addManualAccount: (clientId: string, data: ManualAccountInput) =>
    request<ClientAccount>(`${base(clientId)}/accounts/manual`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateManualAccount: (clientId: string, accountId: string, data: Partial<ManualAccountInput>) =>
    request<ClientAccount>(`${base(clientId)}/accounts/manual/${accountId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  removeManualAccount: (clientId: string, accountId: string) =>
    request<{ status: string; id: string }>(`${base(clientId)}/accounts/manual/${accountId}`, {
      method: "DELETE",
    }),
};

/* ---------------------------------------------------------------- PKCE (X) */

const VERIFIER_KEY = (platform: string) => `cf-oauth-verifier-${platform}`;

function base64Url(bytes: Uint8Array): string {
  let s = "";
  bytes.forEach((b) => (s += String.fromCharCode(b)));
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

/**
 * S256 PKCE pair. The verifier stays in this tab's sessionStorage and is sent
 * only with the code exchange; the provider sees just the challenge.
 */
export async function createPkce(platform: string): Promise<string> {
  const verifier = base64Url(crypto.getRandomValues(new Uint8Array(48)));
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
  try {
    window.sessionStorage.setItem(VERIFIER_KEY(platform), verifier);
  } catch {
    throw new Error("This browser blocked session storage, which the X sign-in needs. Allow site data and try again.");
  }
  return base64Url(new Uint8Array(digest));
}

export function takePkceVerifier(platform: string): string | undefined {
  try {
    const v = window.sessionStorage.getItem(VERIFIER_KEY(platform)) ?? undefined;
    window.sessionStorage.removeItem(VERIFIER_KEY(platform));
    return v;
  } catch {
    return undefined;
  }
}

/** The client id carried in the signed OAuth state (read only — the backend verifies the signature). */
export function clientIdFromState(state: string): string | null {
  try {
    const payload = state.split(".")[1];
    const json = JSON.parse(atob(payload.replace(/-/g, "+").replace(/_/g, "/")));
    return typeof json.cid === "string" ? json.cid : null;
  } catch {
    return null;
  }
}
