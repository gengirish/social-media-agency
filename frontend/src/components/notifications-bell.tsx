"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

interface Notification {
  id: string;
  type: string;
  title: string;
  body: string;
  read: boolean;
  created_at: string | null;
}

export function NotificationsBell() {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);
  // Defaults to true so an older backend, or a failed request, behaves the way it always did.
  // Only an explicit `producers_wired: false` suppresses the re-fetch.
  const [producersWired, setProducersWired] = useState(true);
  const [emptyReason, setEmptyReason] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  // Once on mount for the badge, and again when the panel is opened. Nothing on a timer.
  //
  // This polled every 30s. `GET /notifications` answers `producers_wired: false` because
  // nothing in the backend calls `create_notification()`, so that timer re-fetched a list
  // that could not change — roughly 2,880 requests a day per open tab, every one of them
  // returning the same empty array.
  //
  // Deliberately **not** server-sent events, even though the app already speaks SSE for
  // campaign progress. `backend/fly.toml` sets `[http_service.concurrency] type =
  // 'connections'`, so an open SSE stream is a counted connection and would hold a machine
  // awake for as long as a tab is open — the exact opposite of why the poll was removed.
  // A stream for an event source that emits nothing costs a warm machine to deliver silence.
  useEffect(() => {
    void loadNotifications();
  }, []);

  useEffect(() => {
    if (!open) return;
    function handlePointerDown(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, [open]);

  async function loadNotifications() {
    try {
      const data = await api.getNotifications();
      const items = (data.items || []) as Notification[];
      setNotifications(items);
      setUnread(data.unread_count || 0);
      setProducersWired(data.producers_wired !== false);
      setEmptyReason(data.reason ?? null);
    } catch {
      // silently fail
    }
  }

  function togglePanel() {
    const next = !open;
    setOpen(next);
    // Opening the panel is the only moment this list is actually read, so it is the only
    // moment worth spending a request on. Skipped entirely while the backend reports no
    // producers, because then the answer is known in advance.
    if (next && producersWired) void loadNotifications();
  }

  async function markRead(id: string) {
    try {
      await api.markNotificationRead(id);
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, read: true } : n))
      );
      setUnread((prev) => Math.max(0, prev - 1));
    } catch {
      // silently fail
    }
  }

  async function markAllRead() {
    try {
      await api.markAllNotificationsRead();
      setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
      setUnread(0);
    } catch {
      // silently fail
    }
  }

  return (
    <div className="relative" ref={rootRef}>
      <button
        type="button"
        onClick={togglePanel}
        className="relative rounded-lg p-2 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900"
        aria-expanded={open}
        aria-label="Notifications"
      >
        <svg
          className="h-5 w-5"
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth={1.5}
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0"
          />
        </svg>
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-0.5 text-[10px] font-bold text-white">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full z-50 mt-2 w-80 rounded-lg border border-slate-200 bg-white shadow-xl">
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
            <h3 className="text-sm font-semibold text-slate-900">Notifications</h3>
            {unread > 0 && (
              <button
                type="button"
                onClick={markAllRead}
                className="text-xs text-indigo-600 hover:text-indigo-500"
              >
                Mark all read
              </button>
            )}
          </div>
          <div className="max-h-80 overflow-y-auto">
            {notifications.length === 0 ? (
              // Nothing in the backend produces notifications yet (no caller of
              // create_notification), so an empty list must not read as
              // "you're all caught up".
              <div className="px-4 py-6 text-center">
                <p className="text-sm text-slate-500">No notifications</p>
                <p className="mt-1 text-xs text-slate-400">
                  {emptyReason ??
                    "Notifications are not generated yet — this list stays empty regardless of campaign activity."}
                </p>
              </div>
            ) : (
              notifications.map((n) => (
                <button
                  key={n.id}
                  type="button"
                  onClick={() => !n.read && markRead(n.id)}
                  className={`w-full border-b border-slate-100 px-4 py-3 text-left transition-colors hover:bg-slate-50 ${
                    !n.read ? "bg-indigo-50/40" : ""
                  }`}
                >
                  <p className="text-sm font-medium text-slate-900">{n.title}</p>
                  {n.body && <p className="mt-1 text-xs text-slate-600">{n.body}</p>}
                  {n.created_at && (
                    <p className="mt-1 text-[10px] text-slate-400">
                      {new Date(n.created_at).toLocaleString()}
                    </p>
                  )}
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
