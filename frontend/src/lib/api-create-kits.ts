/*
 * Create › Email and Create › Launch. Generation goes through these endpoints;
 * listing and deleting the saved drafts go through the shared asset store
 * (`foundationApi.listAssets` / `deleteAsset`). Nothing here sends anything —
 * these are drafts the human copies into the tool they already use.
 */
import { request, apiErrorCode } from "@/lib/api";
import type { CreativeAsset } from "@/lib/api-foundation";

export type EmailCampaignType = "welcome" | "onboarding" | "reengagement" | "update" | "milestone";

/** Cadence's CAMPAIGN_TYPE_LABELS, in the same order. */
export const EMAIL_CAMPAIGN_TYPES: { id: EmailCampaignType; label: string }[] = [
  { id: "welcome", label: "Welcome (Day 0)" },
  { id: "onboarding", label: "Onboarding nudge" },
  { id: "reengagement", label: "Re-engagement" },
  { id: "update", label: "Product update" },
  { id: "milestone", label: "Milestone" },
];

export interface EmailCampaignPayload {
  campaign_type: EmailCampaignType;
  subject_line: string;
  subject_line_b: string;
  preview_text: string;
  segment_note: string;
  send_time_note: string;
  body: string;
}

export interface LaunchKitPayload {
  tagline: string;
  ph_description: string;
  maker_comment: string;
  launch_timing_note: string;
  why_now_hook: string;
  press_pitch_subject: string;
  press_pitch_body: string;
  /** True when a PRFAQ stress-test existed and was fed into this kit. */
  prfaq_addressed?: boolean;
}

export interface CommunityKitPayload {
  channel_structure: string[];
  welcome_message: string;
  engagement_prompts: string[];
  event_announcement_template: string;
  moderation_note: string;
}

export interface OutreachPitchPayload {
  target_type: string;
  subject: string;
  pitch_body: string;
  specific_ask: string;
  economics_note: string;
}

export interface QA {
  question: string;
  answer: string;
}

export interface Prfaq {
  press_release_headline: string;
  press_release_body: string;
  customer_faq: QA[];
  internal_faq: QA[];
  weakest_claim: string;
  sharper_version_note: string;
  generated_at?: string;
}

export type LaunchMode = "launch_kit" | "community_kit" | "outreach_pitch";

export const createKitsApi = {
  generateEmail: (clientId: string, campaignType: EmailCampaignType, signal?: AbortSignal) =>
    request<CreativeAsset<EmailCampaignPayload>>("/api/v1/create/email/generate", {
      method: "POST",
      body: JSON.stringify({ client_id: clientId, campaign_type: campaignType }),
      signal,
    }),
  generateLaunch: <P>(clientId: string, mode: LaunchMode, signal?: AbortSignal) =>
    request<CreativeAsset<P>>("/api/v1/create/launch/generate", {
      method: "POST",
      body: JSON.stringify({ client_id: clientId, mode }),
      signal,
    }),
  getPrfaq: (clientId: string) =>
    request<{ prfaq: Prfaq | null }>(`/api/v1/create/launch/prfaq?client_id=${encodeURIComponent(clientId)}`),
  /**
   * Run the PRFAQ stress-test. Spends one generation.
   *
   * `note` is what is being launched, in the user's own words — optional, asked
   * for on the confirm step (CF-13). Without it the model had only the brand
   * profile and filled the gap itself, which is how a run ended up quoting
   * people who do not exist.
   */
  runPrfaq: (clientId: string, note = "", signal?: AbortSignal) =>
    request<{ prfaq: Prfaq }>("/api/v1/create/launch/prfaq", {
      method: "POST",
      body: JSON.stringify({ client_id: clientId, note }),
      signal,
    }),
};

/** 409 brand_profile_required — the client has no brand profile to write from. */
export function isBrandProfileRequired(err: unknown): boolean {
  return apiErrorCode(err) === "brand_profile_required";
}

/** Clipboard write that reports success instead of throwing (blocked in some contexts). */
export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}
