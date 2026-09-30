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
 *
 * That last sentence holds for a *connected* channel only. A manual channel has
 * no publisher behind it and a scheduled piece there is a reminder to a human, so
 * scheduling is allowed for every platform — ask {@link scheduleUnavailableReason}
 * rather than this map when the question is whether a time can be set.
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

/**
 * Whether a *new* direct OAuth connection can be started anywhere in the app.
 *
 * Off: manual channels ("pages you manage yourself") are the supported way to add a
 * channel, and Setup shows each platform as "Coming soon". Nothing underneath is
 * removed or stubbed — the authorize route, the consent sheet, the PKCE callback
 * page and the publishers are all intact and tested, so flipping this to `true` is the
 * whole re-enable.
 *
 * Read by `setup/connected-accounts.tsx` and the `/welcome` onboarding step so the two
 * cannot disagree. An account already connected keeps working, keeps showing, and can
 * still be disconnected.
 */
export const OAUTH_CONNECT_ENABLED = false;

/** True when the backend has a working publisher for this platform. */
export function canPublish(platform: string | null | undefined): boolean {
  return publishUnavailableReason(platform) === null;
}

/**
 * Why scheduling this piece would only produce a failure later, or `null`.
 *
 * Scheduling used to be publishing on a timer, so the publish map answered both
 * questions and {@link canPublish} was the only gate anyone needed. On a manual
 * channel it no longer is: the scheduler never hands a manual piece to a publisher
 * — it sees the piece is due, notifies the person who has to post it, and leaves it
 * `scheduled` — so Instagram and TikTok, which have no publisher at all, are
 * schedulable there. `ensure_schedulable` on the backend makes exactly this
 * exception (`docs/manual-publish-plan-260929.md`, Phase 4).
 *
 * Deliberately a wrapper and not a second map. {@link UNAVAILABLE_PUBLISH_PLATFORMS},
 * {@link publishUnavailableReason} and {@link canPublish} stay exactly as strict as
 * they are, because for a *connected* channel a scheduled post really is a publish
 * and refusing it up front is still right. Only the manual case is carved out, and
 * only here.
 */
export function scheduleUnavailableReason(
  platform: string | null | undefined,
  { manual = false }: { manual?: boolean } = {}
): string | null {
  if (manual) return null;
  return publishUnavailableReason(platform);
}

/** True when this piece can be given a time — a reminder on a manual channel, a publish otherwise. */
export function canSchedule(
  platform: string | null | undefined,
  options: { manual?: boolean } = {}
): boolean {
  return scheduleUnavailableReason(platform, options) === null;
}

/**
 * Where a human goes to post by hand, per channel ("Post it yourself").
 *
 * The second honesty map, kept beside {@link UNAVAILABLE_PUBLISH_PLATFORMS} on
 * purpose: one says what the product cannot publish, this one says how a person
 * publishes it instead. Source of truth is the composer table in
 * `docs/manual-publish-plan-260929.md` §1.
 *
 * **The clipboard is the payload carrier; the deep link only lands the user in
 * the right composer.** Only X accepts post text in a URL (`/intent/post`), so
 * `prefill` is true for exactly one entry. For every other channel the composer
 * opens empty and the UI must say "copied — paste it into the composer" rather
 * than implying the text travelled with the link.
 *
 * `preferProfileUrl` marks the channels whose generic composer is a poor guess —
 * a Facebook Page or Instagram account is reached through the page itself — so
 * the channel's own `profile_url` wins when it is on file.
 *
 * A channel absent from this map has **no composer URL anyone has verified**
 * (Phase 1 also allows manual channels on YouTube, Reddit, Threads and Bluesky).
 * Those fall back to the channel's `profile_url`, and to no tab at all when there
 * is none — never invent a composer URL. The caller then says the text is copied
 * and where to paste it.
 */
const MANUAL_COMPOSERS: Record<
  string,
  { url: string | null; prefill: boolean; preferProfileUrl?: boolean }
> = {
  twitter: { url: "https://x.com/intent/post?text=", prefill: true },
  x: { url: "https://x.com/intent/post?text=", prefill: true },
  linkedin: { url: "https://www.linkedin.com/feed/?shareActive=true", prefill: false },
  facebook: { url: "https://business.facebook.com/latest/composer", prefill: false, preferProfileUrl: true },
  instagram: { url: "https://www.instagram.com/", prefill: false, preferProfileUrl: true },
  tiktok: { url: "https://www.tiktok.com/tiktokstudio/upload", prefill: false },
};

/** What a human pastes: body, blank line, `#tag #tag` — the publisher's own shape. */
export function manualPostText(body: string, hashtags: string[] = []): string {
  const tags = hashtags.filter(Boolean).map((t) => `#${t.replace(/^#+/, "")}`).join(" ");
  return tags ? `${body}\n\n${tags}` : body;
}

/** True when this platform's composer link carries the post text with it. Only X does. */
export function prefillsBody(platform: string | null | undefined): boolean {
  if (!platform) return false;
  return MANUAL_COMPOSERS[platform.trim().toLowerCase()]?.prefill === true;
}

/**
 * The composer to open for a hand-posted piece, or `null` when there is nothing
 * verified to open — in which case the text is on the clipboard and the caller
 * must say so instead of opening a tab.
 */
export function manualComposerUrl(
  platform: string | null | undefined,
  { body = "", hashtags = [], profileUrl = null }: { body?: string; hashtags?: string[]; profileUrl?: string | null }
): string | null {
  const key = (platform ?? "").trim().toLowerCase();
  const entry = MANUAL_COMPOSERS[key];
  const profile = profileUrl?.trim() || null;
  // Unknown channel: the page the operator gave us is the only address we trust.
  if (!entry) return profile;
  if (entry.preferProfileUrl && profile) return profile;
  if (entry.prefill) return `${entry.url}${encodeURIComponent(manualPostText(body, hashtags))}`;
  return entry.url ?? profile;
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
