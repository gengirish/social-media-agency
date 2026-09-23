/*
 * Shared API surface for the Cadence-parity screens: the per-client overview
 * behind the client switcher and Welcome, and the creative-asset store every
 * Create screen saves into. Feature screens keep their own modules
 * (api-<feature>.ts) built on the same `request` helper.
 */
import { request, qs } from "@/lib/api";

export interface ClientOverview {
  id: string;
  brand_name: string;
  website_url: string | null;
  has_brand_profile: boolean;
  connected_accounts: number;
  total_posts: number;
  pending: number;
  approved: number;
  scheduled: number;
  published: number;
  failed: number;
  /** Cadence's "Campaign": the human-typed current focus every generator reads. */
  campaign_focus: string | null;
}

export type AssetKind =
  | "blog_post"
  | "comparison_page"
  | "niche_scan"
  | "video_script"
  | "email_campaign"
  | "launch_kit"
  | "community_kit"
  | "outreach_pitch"
  | "ad_set"
  | "advocacy"
  | "strategy_lens";

export interface CreativeAsset<P = Record<string, unknown>> {
  id: string;
  client_id: string;
  kind: AssetKind;
  title: string;
  payload: P;
  source_asset_id: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface AssetListQuery {
  clientId: string;
  kinds?: AssetKind[];
  q?: string;
  limit?: number;
  offset?: number;
}

function assetListPath({ clientId, kinds, q, limit, offset }: AssetListQuery): string {
  const base = qs({ client_id: clientId, q, limit, offset });
  const kindParams = (kinds ?? []).map((k) => `kind=${encodeURIComponent(k)}`).join("&");
  return `/api/v1/assets${base}${kindParams ? `&${kindParams}` : ""}`;
}

export const foundationApi = {
  clientsOverview: () => request<{ items: ClientOverview[] }>("/api/v1/clients/overview"),
  setCampaignFocus: (clientId: string, description: string) =>
    request<{ campaign_focus: string | null }>(`/api/v1/clients/${clientId}/campaign-focus`, {
      method: "PUT",
      body: JSON.stringify({ description }),
    }),
  clearCampaignFocus: (clientId: string) =>
    request<{ campaign_focus: null }>(`/api/v1/clients/${clientId}/campaign-focus`, { method: "DELETE" }),

  listAssets: <P = Record<string, unknown>>(query: AssetListQuery) =>
    request<{ items: CreativeAsset<P>[]; total: number }>(assetListPath(query)),
  getAsset: <P = Record<string, unknown>>(id: string) => request<CreativeAsset<P>>(`/api/v1/assets/${id}`),
  updateAsset: <P = Record<string, unknown>>(id: string, data: { title?: string; payload?: P }) =>
    request<CreativeAsset<P>>(`/api/v1/assets/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteAsset: (id: string) => request<void>(`/api/v1/assets/${id}`, { method: "DELETE" }),
};
