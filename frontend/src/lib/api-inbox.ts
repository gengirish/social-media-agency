/*
 * Inbox API — live X mentions / LinkedIn comments for the active client.
 * Items are fetched from the platforms on every load (short server-side cache);
 * nothing here is seeded. Every account carries an honest status.
 */
import { request, qs } from "@/lib/api";

export type InboxItemType = "mention" | "comment" | "dm";

export type InboxAccountStatus =
  | "ok"
  | "not_connected"
  | "needs_reconnect"
  | "api_access_denied"
  | "rate_limited"
  | "unsupported"
  | "error";

export interface InboxAccount {
  account_id: string | null;
  platform: string;
  handle: string;
  status: InboxAccountStatus;
  message: string;
  retry_after: number | null;
  reply_supported: boolean;
  item_count: number;
  fetched_at: string | null;
  cached: boolean;
}

export interface InboxItem {
  id: string;
  native_id: string;
  platform: string;
  type: InboxItemType;
  author: { name: string; handle: string; avatar: string | null };
  text: string;
  url: string;
  created_at: string | null;
  in_reply_to: { id: string; url: string } | null;
  account_id: string | null;
  read: boolean;
  handled: boolean;
  reply_url: string | null;
}

export interface InboxResponse {
  client_id: string;
  accounts: InboxAccount[];
  items: InboxItem[];
  dms: { available: boolean; reason: string };
}

export interface ReplySuggestion {
  suggestion: string;
  needs_personal_attention: boolean;
}

export interface ModerationIssue {
  severity: "low" | "medium" | "high";
  message: string;
}

export interface ReplySent {
  status: "sent";
  reply_id: string;
  url: string;
  moderation: { status: string; issues: ModerationIssue[] };
}

export const inboxApi = {
  get: (clientId: string, refresh = false) =>
    request<InboxResponse>(`/api/v1/inbox${qs({ client_id: clientId, refresh: refresh || undefined })}`),

  setState: (body: { client_id: string; item_id: string; read?: boolean; handled?: boolean }) =>
    request<{ item_id: string; read: boolean; handled: boolean }>("/api/v1/inbox/items/state", {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  suggest: (
    body: { client_id: string; platform: string; type: InboxItemType; author: string; text: string },
    signal?: AbortSignal
  ) =>
    request<ReplySuggestion>("/api/v1/inbox/suggest-reply", {
      method: "POST",
      body: JSON.stringify(body),
      signal,
    }),

  reply: (body: { client_id: string; account_id: string; item_id: string; text: string; override?: boolean }) =>
    request<ReplySent>("/api/v1/inbox/reply", { method: "POST", body: JSON.stringify(body) }),
};
