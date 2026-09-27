/*
 * Insights + Settings (Cadence parity) API: per-client computed insights, the
 * customer advocacy agent, the activity log, the JSON export and posting prefs.
 * Every number here comes from the server's real rows; a ratio below its
 * minimum sample arrives as `value: null` with `status: "insufficient_data"`.
 */
import { request, qs } from "@/lib/api";
import type { CreativeAsset } from "@/lib/api-foundation";

export interface GatedRate {
  status: "available" | "insufficient_data";
  value: number | null;
  count: number;
  n: number;
  needed: number;
}

export interface QualityRow {
  platform: string;
  total: number;
  kept: number;
  edited: number;
  discarded: number;
  kept_pct: number;
  edited_pct: number;
  discarded_pct: number;
  regenerated: number;
}

export interface Recommendation {
  id: string;
  text: string;
  platform?: string;
  action_label?: string;
  href?: string;
}

export interface ThresholdRule {
  id: string;
  rule: string;
  have: number;
  needed: number;
  status: "evaluated" | "insufficient_data";
}

export interface InsightsSummary {
  client_id: string;
  min_sample: number;
  total_posts: number;
  funnel: {
    pending: number;
    approved: number;
    scheduled: number;
    published: number;
    failed: number;
    rejected: number;
  };
  connected_platforms: string[];
  by_platform: { platform: string; count: number; connected: boolean }[];
  publish: { attempts: number; published: number; failed: number; success: GatedRate };
  moderation: { checks: number; flagged: number; clean: GatedRate };
  quality_signal: {
    rows: QualityRow[];
    rates: {
      approved_without_edit: GatedRate;
      moderation_flag_rate: GatedRate;
      failed_publish_rate: GatedRate;
    };
  };
  engagement: {
    status: "available" | "unavailable";
    posts_measured: number;
    by_platform: { platform: string; posts: number; avg_engagement: number; total_engagement: number }[];
  };
  recommendations: Recommendation[];
  thresholds: ThresholdRule[];
}

export interface AdvocacyPayload {
  reviewRequestMessage: string;
  caseStudyOutline: string[];
  socialProofSnippet: string;
  facts: Record<string, number>;
}

export interface ActivityItem {
  id: string;
  action: string;
  detail: string;
  at: string;
}

export const VOICE_OPTIONS = ["Blunt & technical", "Friendly & casual", "Bold & punchy", "Calm & authoritative"] as const;
export const CADENCE_OPTIONS = [3, 5, 7, 14] as const;

export interface PostingPrefs {
  voice_register?: (typeof VOICE_OPTIONS)[number];
  cadence_per_week?: (typeof CADENCE_OPTIONS)[number];
  updated_at?: string;
}

export interface ClientExport {
  exported_at: string;
  client: { brand_name: string } & Record<string, unknown>;
  counts: Record<string, number>;
  [key: string]: unknown;
}

export const insightsApi = {
  summary: (clientId: string) =>
    request<InsightsSummary>(`/api/v1/insights/summary${qs({ client_id: clientId })}`),
  generateAdvocacy: (clientId: string, signal?: AbortSignal) =>
    request<CreativeAsset<AdvocacyPayload>>("/api/v1/insights/advocacy", {
      method: "POST",
      body: JSON.stringify({ client_id: clientId }),
      signal,
    }),
  activity: (clientId: string) =>
    request<{ items: ActivityItem[] }>(`/api/v1/workspace/activity${qs({ client_id: clientId })}`),
  exportClient: (clientId: string) =>
    request<ClientExport>(`/api/v1/workspace/export${qs({ client_id: clientId })}`),
  getPostingPrefs: (clientId: string) =>
    request<{ posting_prefs: PostingPrefs }>(`/api/v1/workspace/posting-prefs${qs({ client_id: clientId })}`),
  setPostingPrefs: (clientId: string, prefs: PostingPrefs) =>
    request<{ posting_prefs: PostingPrefs }>(`/api/v1/workspace/posting-prefs${qs({ client_id: clientId })}`, {
      method: "PUT",
      body: JSON.stringify(prefs),
    }),
};

/** Cadence's timeAgo. */
export function timeAgo(iso: string, now: number = Date.now()): string {
  const diffSec = Math.floor((now - new Date(iso).getTime()) / 1000);
  if (diffSec < 60) return "just now";
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  return `${Math.floor(diffHr / 24)}d ago`;
}
