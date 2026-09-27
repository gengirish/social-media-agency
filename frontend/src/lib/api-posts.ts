/*
 * Posts › Queue and Calendar (Cadence parity): generate / regenerate / creative
 * brief / manual post / delete, the active client's channels, and the
 * client-scoped calendar. Backend: routers/post_studio.py, routers/publishing.py.
 *
 * Nothing here can approve, schedule or publish — every post these calls
 * create or rewrite comes back Pending (`draft`).
 */
import { qs, request, type QueuePost } from "@/lib/api";

/** The seven fields of the Creative Director's brief (agents/post_writer.py BRIEF_FIELDS). */
export interface CreativeBrief {
  visualConcept: string;
  composition: string;
  style: string;
  colorDirection: string;
  textOverlay: string;
  aspectRatio: string;
  altText: string;
  generated_at?: string;
}

export const BRIEF_ROWS: [keyof CreativeBrief, string][] = [
  ["visualConcept", "Concept"],
  ["composition", "Composition"],
  ["style", "Style"],
  ["colorDirection", "Colour"],
  ["textOverlay", "Text overlay"],
  ["aspectRatio", "Aspect ratio"],
  ["altText", "Alt text"],
];

export interface CalendarPost {
  id: string;
  title: string;
  body: string;
  hashtags: string[];
  platform: string;
  status: string;
  scheduled_at: string | null;
  published_at: string | null;
  client_id: string;
  campaign_id: string | null;
}

/** Hard caps, mirroring PLATFORM_CHAR_LIMITS (content_writer.PLATFORM_GUIDELINES). */
export const PLATFORM_LIMITS: Record<string, number> = {
  twitter: 280,
  linkedin: 3000,
  instagram: 2200,
  facebook: 63206,
  tiktok: 2200,
};

/** What the publisher actually sends: body, blank line, `#tag #tag`. */
export function renderedLength(body: string, hashtags: string[] = []): number {
  if (!hashtags.length) return body.length;
  return body.length + 2 + hashtags.map((t) => `#${t}`).join(" ").length;
}

export const postStudioApi = {
  channels: (clientId: string) =>
    request<{ connected: string[]; supported: string[] }>(
      `/api/v1/post-studio/channels${qs({ client_id: clientId })}`
    ),

  generate: (
    data: { client_id: string; platform: string; context_note?: string; planned_for?: string },
    signal?: AbortSignal
  ) => request<QueuePost>("/api/v1/content/generate", { method: "POST", body: JSON.stringify(data), signal }),

  createManual: (data: { client_id: string; platform: string; body: string; planned_for?: string }) =>
    request<QueuePost>("/api/v1/content", { method: "POST", body: JSON.stringify(data) }),

  regenerate: (id: string, signal?: AbortSignal) =>
    request<QueuePost>(`/api/v1/content/${id}/regenerate`, { method: "POST", signal }),

  creativeBrief: (id: string, signal?: AbortSignal) =>
    request<QueuePost>(`/api/v1/content/${id}/creative-brief`, { method: "POST", signal }),

  remove: (id: string) => request<void>(`/api/v1/content/${id}`, { method: "DELETE" }),

  /** Includes Pending/Approved posts that carry a planned day, and failed ones. */
  calendar: async (start: string, end: string, clientId?: string | null) => {
    const data = await request<{ items: CalendarPost[] }>(
      `/api/v1/publishing/calendar${qs({ start, end, client_id: clientId ?? undefined, include_pending: true })}`
    );
    return data.items ?? [];
  },
};

// --- Pure helpers (ported from Cadence's code.jsx) ----------------------------

/** A scheduled post whose time has passed without it going out. */
export function isOverdue(post: { status: string; scheduled_at?: string | null }, now = Date.now()): boolean {
  if (!post.scheduled_at || post.status !== "scheduled") return false;
  const t = new Date(post.scheduled_at).getTime();
  return Number.isFinite(t) && t < now;
}

/** "due 5m ago" / "due 3h ago" / "due 2d ago", or "" when not overdue. */
export function overdueLabel(post: { status: string; scheduled_at?: string | null }, now = Date.now()): string {
  if (!isOverdue(post, now)) return "";
  const mins = Math.floor((now - new Date(post.scheduled_at as string).getTime()) / 60000);
  if (mins < 60) return `due ${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `due ${hrs}h ago`;
  return `due ${Math.floor(hrs / 24)}d ago`;
}

/** Blob → object URL → synthetic anchor click → revoke. */
export function downloadTextFile(filename: string, text: string) {
  const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

/** A typical posting window at a non-round minute — suggestions that don't read as automated. */
export function randomPostTime(): { hour: number; minute: number } {
  const hours = [8, 9, 10, 11, 13, 14, 15, 16, 17];
  return { hour: hours[Math.floor(Math.random() * hours.length)], minute: 1 + Math.floor(Math.random() * 58) };
}

export function isAbortError(err: unknown): boolean {
  return err instanceof DOMException && err.name === "AbortError";
}

export function creativeBriefOf(post: { metadata_?: Record<string, unknown> | null }): CreativeBrief | null {
  const b = post.metadata_?.creative_brief;
  return b && typeof b === "object" ? (b as CreativeBrief) : null;
}
