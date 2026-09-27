/*
 * Create › Content — blog post, comparison page, niche scan, video script and
 * the AI-search pack. Generation lives at /api/v1/create/content/*; the saved
 * items are ordinary creative assets (list/delete via foundationApi).
 * Backend: backend/src/agency/routers/create_content.py.
 *
 * Payload field names are Cadence's (camelCase) so the cards map 1:1.
 */
import { request } from "@/lib/api";
import type { AssetKind, CreativeAsset } from "@/lib/api-foundation";

export type ContentMode = "scan" | "seo" | "compare" | "video";

export const MODE_KIND: Record<ContentMode, AssetKind> = {
  scan: "niche_scan",
  seo: "blog_post",
  compare: "comparison_page",
  video: "video_script",
};

export interface AiSeoPack {
  citableSummary: string;
  faq: { question: string; answer: string }[];
  entityClarityNotes: string;
  llmsTxtEntry: string;
}

export interface BlogPayload {
  keyword: string;
  searchIntent: string;
  title: string;
  metaDescription: string;
  outline: string[];
  body: string;
  aiSeoPack?: AiSeoPack;
  /** Set when the post was written from a niche scan's gap. */
  fromGap?: string;
}

/** Provenance stamped server-side: whether live web search actually ran. */
export interface WebResearch {
  status: "ok" | "unavailable";
  reason: string | null;
  retrievedAt: string | null;
  sources: { id: string; competitor: string; title: string; url: string; domain: string | null; publishedDate: string | null }[];
}

export interface ComparisonPayload {
  competitorName: string;
  title: string;
  metaDescription: string;
  introParagraph: string;
  comparisonPoints: { dimension: string; us: string; them: string }[];
  honestWhereTheyWin: string;
  cta: string;
  sourcesNote?: string;
  webResearch?: WebResearch;
}

export interface NicheScanPayload {
  competitorNames: string[];
  scannedAt: string;
  angles: { angle: string; usedBy: string[]; saturation: "high" | "medium" | "low"; note: string }[];
  gapRecommendation: string;
  sourcesNote?: string;
  webResearch?: WebResearch;
}

export interface VideoScriptPayload {
  hook: string;
  scriptBeats: string[];
  onScreenText: string[];
  audioStyleNote: string;
  caption: string;
  hashtags: string[];
}

export type AnyContentPayload = BlogPayload | ComparisonPayload | NicheScanPayload | VideoScriptPayload;
export type ContentAsset = CreativeAsset<AnyContentPayload>;

const BASE = "/api/v1/create/content";

function post<P>(path: string, body: unknown, signal?: AbortSignal) {
  return request<CreativeAsset<P>>(`${BASE}${path}`, {
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });
}

export const createContentApi = {
  blog: (clientId: string, signal?: AbortSignal) => post<BlogPayload>("/blog", { client_id: clientId }, signal),
  comparison: (clientId: string, competitorName: string, signal?: AbortSignal) =>
    post<ComparisonPayload>("/comparison", { client_id: clientId, competitor_name: competitorName }, signal),
  nicheScan: (clientId: string, competitorNames: string[], signal?: AbortSignal) =>
    post<NicheScanPayload>("/niche-scan", { client_id: clientId, competitor_names: competitorNames }, signal),
  videoScript: (clientId: string, signal?: AbortSignal) =>
    post<VideoScriptPayload>("/video-script", { client_id: clientId }, signal),
  blogFromGap: (scanId: string, signal?: AbortSignal) =>
    post<BlogPayload>(`/niche-scan/${scanId}/blog`, undefined, signal),
  optimizeForAi: (blogId: string, signal?: AbortSignal) =>
    post<BlogPayload>(`/blog/${blogId}/ai-seo`, undefined, signal),
};

/*
 * Cadence's findSimilarScan: warn, never block, before burning a generation on
 * a competitor set already scanned. Exact match, or >= 60% name overlap.
 * Mirrors services/create_content.py::find_similar_scan (tested there).
 */
export function findSimilarScan(
  names: string[],
  scans: ContentAsset[]
): { scan: ContentAsset; shared: string[]; isExact: boolean } | null {
  const normalized = Array.from(new Set(names.map((n) => n.trim().toLowerCase()).filter(Boolean)));
  if (normalized.length < 2) return null;
  let best: { scan: ContentAsset; shared: string[]; isExact: boolean } | null = null;
  for (const scan of scans) {
    const p = scan.payload as NicheScanPayload;
    const scanSet = new Set((p.competitorNames ?? []).map((n) => n.trim().toLowerCase()));
    if (scanSet.size === 0) continue;
    const shared = normalized.filter((n) => scanSet.has(n));
    if (shared.length === 0) continue;
    const isExact = shared.length === normalized.length && shared.length === scanSet.size;
    const overlap = shared.length / Math.max(normalized.length, scanSet.size);
    if ((isExact || overlap >= 0.6) && (!best || isExact || shared.length > best.shared.length)) {
      best = { scan, shared, isExact };
    }
  }
  return best;
}

/** Comma-separated names → trimmed, de-duplicated, max 5 (Cadence's scanNames). */
export function parseScanNames(input: string): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of input.split(",")) {
    const name = raw.trim();
    if (name && !seen.has(name.toLowerCase())) {
      seen.add(name.toLowerCase());
      out.push(name);
    }
  }
  return out.slice(0, 5);
}

/** The text Copy and Export produce — markdown, so the export opens cleanly anywhere. */
export function draftMarkdown(kind: AssetKind, payload: AnyContentPayload): string {
  if (kind === "blog_post") {
    const p = payload as BlogPayload;
    const parts = [`# ${p.title}`, `> ${p.metaDescription}`, `**Keyword:** ${p.keyword}`, p.body];
    if (p.aiSeoPack) {
      parts.push(
        "## Optimized for AI search",
        `**Citable summary:** ${p.aiSeoPack.citableSummary}`,
        p.aiSeoPack.faq.map((qa) => `**${qa.question}**\n${qa.answer}`).join("\n\n"),
        `**Entity clarity:** ${p.aiSeoPack.entityClarityNotes}`,
        "`" + p.aiSeoPack.llmsTxtEntry + "`"
      );
    }
    return parts.join("\n\n");
  }
  if (kind === "comparison_page") {
    const p = payload as ComparisonPayload;
    return [
      `# ${p.title}`,
      `> ${p.metaDescription}`,
      p.introParagraph,
      "## Comparison",
      p.comparisonPoints.map((c) => `- **${c.dimension}** — Us: ${c.us} | Them: ${c.them}`).join("\n"),
      `## Where ${p.competitorName} honestly wins`,
      p.honestWhereTheyWin,
      p.cta,
      p.sourcesNote ? `_${p.sourcesNote}_` : "",
    ]
      .filter(Boolean)
      .join("\n\n");
  }
  if (kind === "niche_scan") {
    const p = payload as NicheScanPayload;
    return [
      `# Niche scan — vs ${p.competitorNames.join(", ")}`,
      p.angles
        .map((a) => `- **${a.angle}** (${a.saturation} saturation) — used by ${a.usedBy.join(", ") || "—"}\n  ${a.note}`)
        .join("\n"),
      `## Gap to consider\n${p.gapRecommendation}`,
      p.sourcesNote ? `_${p.sourcesNote}_` : "",
      ...(p.webResearch?.sources.length
        ? ["## Sources", p.webResearch.sources.map((s) => `- [${s.title}](${s.url})`).join("\n")]
        : []),
    ]
      .filter(Boolean)
      .join("\n\n");
  }
  const p = payload as VideoScriptPayload;
  return [
    "# Short-form video script",
    `**Hook:** ${p.hook}`,
    p.scriptBeats.map((b, i) => `${i + 1}. ${b}`).join("\n"),
    `**On-screen text:**\n${p.onScreenText.map((t) => `- "${t}"`).join("\n")}`,
    `**Audio:** ${p.audioStyleNote}`,
    `**Caption:** ${p.caption}\n${p.hashtags.map((h) => `#${h}`).join(" ")}`,
  ].join("\n\n");
}

/** Cadence's downloadTextFile (Blob → object URL → synthetic click → revoke). */
export function downloadTextFile(filename: string, text: string, type = "text/markdown;charset=utf-8") {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function exportFilename(asset: ContentAsset): string {
  const slug = (asset.title || asset.kind).slice(0, 40).replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "").toLowerCase();
  return `${slug || asset.kind}-${asset.id.slice(0, 8)}.md`;
}

// --- Amplify sources ---------------------------------------------------------

/** Asset kinds Amplify accepts as a source — mirrors REPURPOSABLE_ASSET_KINDS server-side. */
export const REPURPOSABLE_KINDS: AssetKind[] = ["blog_post", "comparison_page", "niche_scan", "launch_kit", "video_script"];

export const SOURCE_TYPE_LABEL: Partial<Record<AssetKind, string>> = {
  blog_post: "Blog post",
  comparison_page: "Comparison",
  niche_scan: "Niche scan",
  launch_kit: "Launch kit",
  video_script: "Video script",
};

export interface RepurposeSource {
  id: string;
  kind: AssetKind;
  label: string;
}

function str(v: unknown): string {
  return typeof v === "string" ? v.trim() : "";
}

/**
 * Cadence's collectRepurposeSources over saved assets: every long-form kind is
 * a real source, labelled the way Cadence labels it. Anything without real
 * text is skipped rather than offered empty (the server would 422 it anyway).
 */
export function collectRepurposeSources(assets: CreativeAsset[]): RepurposeSource[] {
  const out: RepurposeSource[] = [];
  for (const a of assets) {
    const p = (a.payload ?? {}) as Record<string, unknown>;
    if (a.kind === "blog_post" && str(p.body)) {
      out.push({ id: a.id, kind: a.kind, label: str(p.title) || str(p.keyword) || a.title || "Blog post" });
    } else if (a.kind === "comparison_page" && (str(p.introParagraph) || str(p.title))) {
      out.push({ id: a.id, kind: a.kind, label: `vs. ${str(p.competitorName) || "competitor"}` });
    } else if (a.kind === "niche_scan" && str(p.gapRecommendation)) {
      const names = Array.isArray(p.competitorNames) ? (p.competitorNames as unknown[]).map(String).join(", ") : "";
      out.push({ id: a.id, kind: a.kind, label: `Niche scan: ${names}` });
    } else if (
      a.kind === "launch_kit" &&
      (str(p.announcementPost) || str(p.announcement_post) || str(p.summary))
    ) {
      out.push({ id: a.id, kind: a.kind, label: a.title || "Launch kit" });
    } else if (a.kind === "video_script" && str(p.hook)) {
      out.push({ id: a.id, kind: a.kind, label: str(p.hook) || "Video script" });
    }
  }
  return out;
}
