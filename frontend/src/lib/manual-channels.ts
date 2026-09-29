"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { setupApi } from "@/lib/api-setup";
import type { ManualChannel } from "@/components/posts/post-card";

/**
 * Which of each client's channels are registered by hand (`status: "manual"`).
 *
 * A manual channel has no tokens, so the product cannot post to it: the UI must offer
 * "Post it yourself" instead of Publish now, and must never tell the user that
 * CampaignForge will publish at a scheduled time. Every screen that shows posts needs
 * the same answer, so the fetch lives here rather than in each page — the Queue and the
 * Calendar drifting apart on this is exactly the failure that would put "publishes to
 * your live connected account" on a page the product cannot reach.
 *
 * Read from Setup's own account list rather than a new endpoint. Keyed client id ->
 * platform, because the "all clients" scope shows posts from several clients at once and
 * the mode is per channel, not per org.
 *
 * **A failed read leaves the entry absent, which keeps the OAuth controls.** A 403 or a
 * dropped request must never turn a connected channel into a manual one. One read per
 * client per session; a client is not retried after a failure, so a transient error
 * hides "Post it yourself" until reload.
 */
export function useManualChannels(clientIds: (string | null | undefined)[]) {
  const [channels, setChannels] = useState<Record<string, Record<string, ManualChannel>>>({});
  const fetched = useRef<Set<string>>(new Set());
  const key = Array.from(new Set(clientIds.filter(Boolean) as string[]))
    .sort()
    .join(",");

  useEffect(() => {
    const ids = key.split(",").filter((id) => id && !fetched.current.has(id));
    if (!ids.length) return;
    ids.forEach((id) => fetched.current.add(id));
    ids.forEach((id) => {
      setupApi
        .listAccounts(id)
        .then((res) => {
          const byPlatform: Record<string, ManualChannel> = {};
          res.accounts
            .filter((a) => a.status === "manual")
            .forEach((a) => {
              byPlatform[a.platform.toLowerCase()] = { profileUrl: a.profile_url };
            });
          setChannels((prev) => ({ ...prev, [id]: byPlatform }));
        })
        .catch(() => {
          // Left unknown on purpose — see the doc comment above.
        });
    });
  }, [key]);

  /** The manual channel for this client + platform, or `null` when it is not one. */
  return useCallback(
    (clientId: string | null | undefined, platform: string | null | undefined): ManualChannel | null =>
      (clientId && channels[clientId]?.[(platform ?? "").toLowerCase()]) || null,
    [channels]
  );
}
