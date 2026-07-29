/**
 * Product analytics client — session, page-view, and feature-adoption signals
 * for the beta metrics dashboard (docs/beta-testing-plan.md §7).
 *
 * Pipeline and error events are authored server-side; this module only sends
 * the four browser-observable events the backend accepts.
 *
 * Session model: a session starts on first activity and ends when the page is
 * hidden. Returning to a visible tab starts a new session. That keeps exactly
 * one `session_ended` per session id, so duration percentiles stay meaningful.
 */

import { API_BASE_URL, getAuthToken } from "./api";

type EventName = "session_started" | "session_ended" | "page_view" | "feature_used";

interface QueuedEvent {
  name: EventName;
  session_id: string;
  path?: string;
  feature?: string;
  duration_ms?: number;
  occurred_at: string;
  properties?: Record<string, unknown>;
}

const FLUSH_INTERVAL_MS = 10_000;
const MAX_BATCH = 50;

let queue: QueuedEvent[] = [];
let flushTimer: ReturnType<typeof setInterval> | null = null;
let sessionId = "";
let sessionStartedAt = 0;
let started = false;

function newSessionId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID().replace(/-/g, "").slice(0, 32);
  }
  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
}

function enqueue(event: Omit<QueuedEvent, "session_id" | "occurred_at">) {
  if (!sessionId) return;
  queue.push({ ...event, session_id: sessionId, occurred_at: new Date().toISOString() });
  if (queue.length >= MAX_BATCH) void flush();
}

/**
 * Send queued events. Failures drop the batch rather than retrying — analytics
 * must never grow unbounded or interfere with the app.
 */
async function flush(keepalive = false): Promise<void> {
  if (queue.length === 0) return;

  const events = queue.slice(0, MAX_BATCH);
  queue = queue.slice(MAX_BATCH);

  try {
    const token = await getAuthToken();
    if (!token) return;

    await fetch(`${API_BASE_URL}/api/v1/events`, {
      method: "POST",
      keepalive,
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ events }),
    });
  } catch {
    // Swallow: a dropped analytics batch is not a user-facing failure.
  }
}

function startSession() {
  sessionId = newSessionId();
  sessionStartedAt = Date.now();
  enqueue({ name: "session_started" });
}

function endSession() {
  if (!sessionId) return;
  enqueue({ name: "session_ended", duration_ms: Date.now() - sessionStartedAt });
  sessionId = "";
  void flush(true);
}

function onVisibilityChange() {
  if (document.visibilityState === "hidden") {
    endSession();
  } else if (!sessionId) {
    startSession();
  }
}

/** Idempotent; safe to call from a mounted component. Returns a teardown fn. */
export function initAnalytics(): () => void {
  if (typeof window === "undefined" || started) return () => {};
  started = true;

  startSession();
  flushTimer = setInterval(() => void flush(), FLUSH_INTERVAL_MS);
  document.addEventListener("visibilitychange", onVisibilityChange);
  window.addEventListener("pagehide", endSession);

  return () => {
    document.removeEventListener("visibilitychange", onVisibilityChange);
    window.removeEventListener("pagehide", endSession);
    if (flushTimer) clearInterval(flushTimer);
    flushTimer = null;
    started = false;
  };
}

export function trackPageView(path: string) {
  enqueue({ name: "page_view", path });
}

/**
 * Record use of a named feature. Feature names drive the adoption table, so
 * keep them stable and lowercase-hyphenated (e.g. "campaign-create").
 */
export function trackFeature(feature: string, properties?: Record<string, unknown>) {
  enqueue({ name: "feature_used", feature, properties });
}
