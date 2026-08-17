/**
 * Which platforms CampaignForge can actually publish to.
 *
 * Source of truth is the backend: `UNAVAILABLE_PUBLISH_PLATFORMS` in
 * `backend/src/agency/services/publishing.py`. This mirror exists so the UI can
 * disable a publish control up front instead of letting the user click through
 * to a 502. Keep the two in sync — when the backend gains a publisher, remove
 * the platform from this map too.
 *
 * Content generation, repurposing, and scheduling work for every platform in
 * the app. Only the final push to the network is gated here.
 */
export const UNAVAILABLE_PUBLISH_PLATFORMS: Record<string, string> = {
  instagram:
    "Instagram publishing is not available yet — it needs media upload through the Meta Graph API. You can still generate and schedule the post, then publish it manually.",
  tiktok:
    "TikTok publishing is not available yet — there is no TikTok publisher or account connection. You can still generate and schedule the post, then publish it manually.",
};

/** Reason this platform cannot be published to, or `null` if it can. */
export function publishUnavailableReason(platform: string | null | undefined): string | null {
  if (!platform) return null;
  return UNAVAILABLE_PUBLISH_PLATFORMS[platform.toLowerCase()] ?? null;
}

/** True when the backend has a working publisher for this platform. */
export function canPublish(platform: string | null | undefined): boolean {
  return publishUnavailableReason(platform) === null;
}
