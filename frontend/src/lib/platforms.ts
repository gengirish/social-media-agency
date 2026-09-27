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

/**
 * Display names for every channel the product names, in one place (CF-19).
 *
 * The API stores lower-case slugs (`linkedin`, `google_ad`, `twitter`), and each
 * screen used to title-case or print them raw, so one channel appeared as
 * "linkedin", "Linkedin" and "LinkedIn" on adjacent pages and ad channels showed
 * as bare "google" and "meta". Route every channel name through
 * {@link platformLabel} instead.
 */
const PLATFORM_LABELS: Record<string, string> = {
  linkedin: "LinkedIn",
  linkedin_ad: "LinkedIn Ads",
  twitter: "X / Twitter",
  x: "X / Twitter",
  facebook: "Facebook",
  instagram: "Instagram",
  tiktok: "TikTok",
  youtube: "YouTube",
  google: "Google Ads",
  google_ad: "Google Ads",
  meta: "Meta",
  meta_ad: "Meta Ads",
  email: "Email",
  blog: "Blog",
  newsletter: "Newsletter",
};

/**
 * A channel slug as it should be shown to a user.
 *
 * An unknown slug is title-cased rather than dropped — a platform added on the
 * backend should read as "Threads", not vanish from the UI — with underscores
 * and dashes becoming spaces.
 */
export function platformLabel(platform: string | null | undefined): string {
  if (!platform) return "";
  const key = platform.trim().toLowerCase();
  if (PLATFORM_LABELS[key]) return PLATFORM_LABELS[key];
  return key
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}
