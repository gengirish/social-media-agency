/**
 * Which platforms CampaignForge can actually publish to.
 *
 * Source of truth is the backend: `UNAVAILABLE_PUBLISH_PLATFORMS` in
 * `backend/src/agency/services/publishing.py`. This mirror exists so the UI can
 * disable a publish control up front instead of letting the user click through
 * to a 502. Keep the two in sync — when the backend gains a publisher, remove
 * the platform from this map too.
 *
 * Generation, repurposing, and approval work for every platform. Scheduling
 * does not: a scheduled post is published by the scheduler, so scheduling an
 * unpublishable platform would only produce a failure later.
 */
export const UNAVAILABLE_PUBLISH_PLATFORMS: Record<string, string> = {
  instagram:
    "Instagram publishing is not available yet — it needs media upload through the Meta Graph API. You can still generate and approve the post, then publish it manually — scheduling is off for the same reason.",
  tiktok:
    "TikTok publishing is not available yet — there is no TikTok publisher or account connection. You can still generate and approve the post, then publish it manually — scheduling is off for the same reason.",
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
