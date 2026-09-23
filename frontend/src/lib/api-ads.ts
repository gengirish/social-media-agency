/*
 * Create › Ads API. Generation lives at /api/v1/create/ads; saved sets are
 * ordinary creative assets (kind "ad_set"), so list/delete reuse foundationApi.
 *
 * Copy and structure only — nothing here talks to an ad account.
 */
import { request } from "@/lib/api";
import { foundationApi, type CreativeAsset } from "@/lib/api-foundation";

export type AdNetwork = "google" | "meta";

export interface AdModeration {
  /** "unavailable" = the check did not run (fail-open), not "passed". */
  status: "ok" | "unavailable";
  flagged: boolean;
  issues: string[];
}

export interface Sitelink {
  text: string;
  desc1: string;
  desc2: string;
}

export interface KeywordTheme {
  intent: string;
  keywords: string[];
  note: string;
}

export interface AdSetPayload {
  network: AdNetwork;
  // Google
  headlines?: string[];
  descriptions?: string[];
  paths?: string[];
  sitelinks?: Sitelink[];
  callouts?: string[];
  keyword_themes?: KeywordTheme[];
  negative_keywords?: string[];
  structure_note?: string;
  // Meta
  primary_texts?: string[];
  cta?: string;
  cta_reason?: string;
  creative_direction?: string;
  audience_angle?: string;
  special_ad_category_note?: string;
  // Guardrails
  limit_warnings?: string[];
  trademark_risks?: string[];
  personal_attribute_risks?: { sentence: string; term: string }[];
  moderation?: AdModeration;
}

export type AdSet = CreativeAsset<AdSetPayload>;

export const adsApi = {
  generate: (clientId: string, network: AdNetwork, signal?: AbortSignal) =>
    request<AdSet>("/api/v1/create/ads/generate", {
      method: "POST",
      body: JSON.stringify({ client_id: clientId, network }),
      signal,
    }),
  list: (clientId: string) =>
    foundationApi.listAssets<AdSetPayload>({ clientId, kinds: ["ad_set"], limit: 200 }),
  remove: (id: string) => foundationApi.deleteAsset(id),
};

/** Mirrors services/ad_guardrails.py AD_LIMITS — used only for the per-row counters. */
export const AD_ROW_LIMITS = {
  google: { headlines: 30, descriptions: 90 },
  meta: { primary_texts: 125, headlines: 27, descriptions: 30 },
} as const;

/** Plain-text export, same layout as Cadence's "Copy all". Counts are character counts, not predictions. */
export function adSetText(p: AdSetPayload): string {
  const list = (xs: string[] | undefined, sep = "\n") =>
    (xs ?? []).map((x, i) => `${i + 1}. ${x}  [${x.length}]`).join(sep);
  if (p.network === "google") {
    return [
      "GOOGLE ADS — Responsive Search Ad",
      `HEADLINES (30 char max)\n${list(p.headlines)}`,
      `DESCRIPTIONS (90 char max)\n${list(p.descriptions)}`,
      `DISPLAY PATHS\n${(p.paths ?? []).join(" / ")}`,
      `SITELINKS\n${(p.sitelinks ?? []).map((s) => `${s.text}\n  ${s.desc1}\n  ${s.desc2}`).join("\n\n")}`,
      `CALLOUTS\n${(p.callouts ?? []).join(" · ")}`,
      `KEYWORD THEMES\n${(p.keyword_themes ?? [])
        .map((k) => `[${k.intent}]\n  ${(k.keywords ?? []).join(", ")}\n  ${k.note ?? ""}`)
        .join("\n\n")}`,
      `NEGATIVE KEYWORDS\n${(p.negative_keywords ?? []).join(", ")}`,
      `STRUCTURE\n${p.structure_note ?? ""}`,
    ].join("\n\n");
  }
  return [
    "META ADS (Facebook/Instagram)",
    `PRIMARY TEXT (~125 visible)\n${list(p.primary_texts, "\n\n")}`,
    `HEADLINES (~27 visible on Feed)\n${list(p.headlines)}`,
    `LINK DESCRIPTIONS (often hidden on mobile)\n${list(p.descriptions)}`,
    `CTA BUTTON\n${p.cta ?? ""} — ${p.cta_reason ?? ""}`,
    `CREATIVE DIRECTION\n${p.creative_direction ?? ""}`,
    `AUDIENCE ANGLE\n${p.audience_angle ?? ""}`,
    `SPECIAL AD CATEGORY\n${p.special_ad_category_note ?? ""}`,
  ].join("\n\n");
}
