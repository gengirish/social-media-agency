import { test, expect, type Page } from "@playwright/test";
import { clerkAuth, isClerkConfigured } from "./helpers/auth";

/**
 * Generated media on a Queue card — Phase 5 of docs/media-generation-plan-261009.md.
 *
 * Stubbed rather than seeded, for the same reason manual-publish.spec.ts is: an
 * asset needs a real generation (real fal.ai spend, real media credits) and a
 * manual channel needs a `platform_account` row only Setup can create. What is
 * under test is the card's own behaviour — what it renders, what it offers, and
 * above all what its copy claims.
 *
 * The copy assertions are the point of the file. Product rule 1: the product
 * generates the image and stores it; on a channel a human posts by hand it is
 * downloaded and attached by that human, and nothing may read as though the
 * product attached or posted anything.
 *
 * NOT covered here (needs a backend fixture): the server's own refusals —
 * 402 `media_credit_quota_exceeded`, 402 `media_video_not_in_plan`,
 * 409 `published_locked`, 502 `media_generation_failed`,
 * 503 `media_generation_not_configured` — and `409 media_unscreened` on approve.
 * The error copy for each lives in `mediaErrorReason` in lib/api.ts.
 */

const ORG_ID = "00000000-0000-0000-0000-0000000000a2";
const CLIENT_ID = "00000000-0000-0000-0000-0000000000b2";
const POST_ID = "00000000-0000-0000-0000-0000000000c2";
const BODY = "We cut onboarding from three weeks to one afternoon. Here is the whole playbook.";

const ASSET_HOST = "https://media.cf-test.invalid";
const IMAGE_URL = `${ASSET_HOST}/org/client/post/asset-1.png`;
const THUMB_URL = `${ASSET_HOST}/org/client/post/asset-1-thumb.webp`;
const SECOND_IMAGE_URL = `${ASSET_HOST}/org/client/post/asset-2.png`;
const SECOND_THUMB_URL = `${ASSET_HOST}/org/client/post/asset-2-thumb.webp`;

/** A 1×1 transparent PNG — enough for the browser to resolve every thumbnail. */
const PIXEL = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
  "base64"
);

type Verdict = "provider_only" | "flagged" | "unscreened";

function moderation(verdict: Verdict) {
  if (verdict === "flagged") {
    return {
      status: "flagged",
      reason: "vision",
      issues: [{ severity: "high", message: "The image shows a price we never approved." }],
    };
  }
  // A never-screened asset really does serialise as `{}` — the UI has to read a
  // missing status, not an empty-string one.
  if (verdict === "unscreened") return {};
  // The normal, healthy case for most images: rung 1 ran, was clean, and no vision
  // call was needed. It must render as nothing at all.
  return { status: "unavailable", reason: "provider_only", issues: [] };
}

function asset(verdict: Verdict = "provider_only") {
  return {
    id: "00000000-0000-0000-0000-0000000000f1",
    kind: "image",
    url: IMAGE_URL,
    thumb_url: THUMB_URL,
    width: 1024,
    height: 1024,
    duration_ms: null,
    moderation: moderation(verdict),
  };
}

function secondAsset() {
  return {
    id: "00000000-0000-0000-0000-0000000000f2",
    kind: "image",
    url: SECOND_IMAGE_URL,
    thumb_url: SECOND_THUMB_URL,
    width: 1024,
    height: 1024,
    duration_ms: null,
    moderation: moderation("provider_only"),
    deduped: false,
  };
}

interface PostOptions {
  status?: string;
  /** Media already on the piece. `[]` is the "nothing generated yet" case. */
  media?: ReturnType<typeof asset>[];
}

function post({ status = "approved", media = [] }: PostOptions = {}) {
  return {
    id: POST_ID,
    campaign_id: null,
    client_id: CLIENT_ID,
    content_type: "social_post",
    platform: "instagram",
    title: "Onboarding, cut down",
    body: BODY,
    hashtags: ["onboarding"],
    status,
    ai_generated: true,
    performance_score: null,
    created_at: new Date().toISOString(),
    scheduled_at: null,
    published_at: null,
    media_urls: media.map((m) => m.url),
    media,
    metadata_: {},
  };
}

function json(body: unknown) {
  return { status: 200, contentType: "application/json", body: JSON.stringify(body) };
}

interface StubOptions {
  /** Register the client's Instagram channel as manual (no tokens), the §1A case. */
  manual?: boolean;
  media?: ReturnType<typeof asset>[];
  status?: string;
}

async function stubQueue(page: Page, options: StubOptions = {}) {
  const state = {
    /** Every body sent to `POST /content/{id}/generate-image`, in order. */
    generateCalls: [] as unknown[],
    media: options.media ?? [],
  };

  // Every thumbnail and original resolves, so a missing image is a real failure
  // rather than a stub artefact.
  await page.route(`${ASSET_HOST}/**`, (route) =>
    route.fulfill({ status: 200, contentType: "image/png", body: PIXEL })
  );

  await page.route("**/api/v1/auth/me", (route) =>
    route.fulfill(
      json({
        user_id: "00000000-0000-0000-0000-0000000000d2",
        email: "e2e@example.com",
        role: "owner",
        org_id: ORG_ID,
        account_type: "business",
        capabilities: [
          "read",
          "campaign.run",
          "content.approve",
          "publish.write",
          "publish.manual",
          "content.override",
          "oauth.connect",
          "team.manage",
          "billing.manage",
        ],
      })
    )
  );

  await page.route("**/api/v1/clients/overview", (route) =>
    route.fulfill(
      json({
        items: [
          {
            id: CLIENT_ID,
            brand_name: "Manual Co",
            website_url: null,
            has_brand_profile: true,
            connected_accounts: 1,
            total_posts: 1,
            pending: options.status === "draft" ? 1 : 0,
            approved: options.status === "draft" ? 0 : 1,
            scheduled: 0,
            published: 0,
            failed: 0,
            campaign_focus: null,
          },
        ],
      })
    )
  );

  await page.route("**/api/v1/billing/subscription", (route) =>
    route.fulfill(
      json({
        plan_tier: "starter",
        posts_limit: 200,
        posts_used: 3,
        generations_limit: 100,
        generations_used: 4,
      })
    )
  );

  await page.route("**/api/v1/post-studio/channels*", (route) =>
    route.fulfill(json({ connected: [], supported: ["linkedin", "twitter", "facebook", "instagram"] }))
  );

  await page.route("**/api/v1/clients/*/brand-profile", (route) =>
    route.fulfill(json({ client_id: CLIENT_ID, brand_name: "Manual Co" }))
  );

  await page.route("**/api/v1/setup/*/accounts", (route) => {
    if (!new URL(route.request().url()).pathname.endsWith("/accounts")) return route.continue();
    return route.fulfill(
      json({
        accounts: options.manual
          ? [
              {
                id: "00000000-0000-0000-0000-0000000000e2",
                platform: "instagram",
                account_handle: "manual-co",
                display_name: "Manual Co",
                status: "manual",
                profile_url: "https://www.instagram.com/manualco/",
                connected_at: null,
              },
            ]
          : [],
        oauth: {},
      })
    );
  });

  await page.route("**/api/v1/content?**", (route) => {
    const params = new URL(route.request().url()).searchParams;
    const wanted = params.get("content_status");
    const current = options.status ?? "approved";
    const items = wanted === current ? [post({ status: current, media: state.media })] : [];
    return route.fulfill(
      json({ items, total: items.length, page: 1, per_page: Number(params.get("per_page") ?? 50) })
    );
  });

  await page.route("**/api/v1/content/*/generate-image", (route) => {
    state.generateCalls.push(route.request().postDataJSON() ?? null);
    return route.fulfill(json(secondAsset()));
  });

  return state;
}

async function openQueue(page: Page, tab: RegExp = /approved/i) {
  await page.goto("/content", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: /^queue$/i })).toBeVisible({ timeout: 30000 });
  await page.getByRole("tab", { name: tab }).click();
  await expect(page.getByText(BODY)).toBeVisible({ timeout: 30000 });
}

test.describe("Generated media on a post card", () => {
  test.beforeEach(async ({ page }) => {
    test.skip(!isClerkConfigured(), "Clerk keys not configured");
    await clerkAuth(page);
  });

  test("renders the thumbnail from the derivative, not the original", async ({ page }) => {
    test.setTimeout(120_000);
    await stubQueue(page, { media: [asset()] });
    await openQueue(page);

    const thumb = page.getByRole("img", { name: /generated image for this post/i });
    await expect(thumb).toBeVisible();
    // The ~400px WebP derivative is what a 12-card Queue view may pull (§1B).
    await expect(thumb).toHaveAttribute("src", THUMB_URL);
    await expect(thumb).toHaveAttribute("loading", "lazy");
  });

  test("a clean provider verdict is silent — only a real problem is surfaced", async ({ page }) => {
    test.setTimeout(120_000);
    await stubQueue(page, { media: [asset("provider_only")] });
    await openQueue(page);

    await expect(page.getByRole("img", { name: /generated image for this post/i })).toBeVisible();
    // `provider_only` is the healthy outcome for most images. A badge here would
    // have cried wolf on nearly every asset.
    await expect(page.getByText(/flagged/i)).toHaveCount(0);
    await expect(page.getByText(/hasn't been screened/i)).toHaveCount(0);
    await expect(page.getByText(/didn't run/i)).toHaveCount(0);
  });

  test("a flagged image says so before anyone approves the post", async ({ page }) => {
    test.setTimeout(120_000);
    await stubQueue(page, { status: "draft", media: [asset("flagged")] });
    await openQueue(page, /pending/i);

    await expect(page.getByText(/this image was flagged/i)).toBeVisible();
    await expect(page.getByText(/price we never approved/i)).toBeVisible();
  });

  test("an unscreened image says approval will check it", async ({ page }) => {
    test.setTimeout(120_000);
    await stubQueue(page, { status: "draft", media: [asset("unscreened")] });
    await openQueue(page, /pending/i);

    await expect(page.getByText(/hasn't been screened/i)).toBeVisible();
  });

  test("Create image is live, Get creative brief stays, Short video does not pretend", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    await stubQueue(page);
    await openQueue(page);

    const create = page.getByRole("button", { name: /^create image$/i });
    await expect(create).toBeVisible();
    await expect(create).toBeEnabled();

    // §1F: the brief is the prompt Create image reads, so it stays beside it.
    await expect(page.getByRole("button", { name: /get creative brief/i })).toBeVisible();

    // Phase 8 has no backend at all, so this must stay visibly unavailable.
    const video = page.getByRole("button", { name: /short video/i });
    await expect(video).toBeDisabled();
    await expect(video).toContainText(/soon/i);
  });

  test("Create image calls the endpoint once and shows the new image", async ({ page }) => {
    test.setTimeout(120_000);
    const state = await stubQueue(page);
    await openQueue(page);

    await expect(page.getByRole("img", { name: /generated image for this post/i })).toHaveCount(0);
    await page.getByRole("button", { name: /^create image$/i }).click();

    await expect(page.getByRole("img", { name: /generated image for this post/i })).toHaveCount(1, {
      timeout: 30000,
    });
    expect(state.generateCalls).toHaveLength(1);
    // Nothing left the product: the asset is attached to the piece here, and that
    // is all the success copy may claim.
    await expect(page.getByText(/nothing has been posted/i)).toBeVisible();
  });

  test("the card never drops the visual actions on a non-Instagram platform", async ({ page }) => {
    test.setTimeout(120_000);
    await stubQueue(page, { media: [asset()] });
    // Registered after stubQueue so this one wins: Playwright tries the most
    // recently added route first.
    // `needsVisual = platform === "instagram"` is gone: X and LinkedIn take media
    // too, and on a manual channel every platform does.
    await page.route("**/api/v1/content?**", async (route) => {
      const params = new URL(route.request().url()).searchParams;
      const items =
        params.get("content_status") === "approved"
          ? [{ ...post({ media: [asset()] }), platform: "linkedin" }]
          : [];
      await route.fulfill(
        json({ items, total: items.length, page: 1, per_page: Number(params.get("per_page") ?? 50) })
      );
    });
    await stubQueue(page, { media: [asset()] });
    await openQueue(page);

    await expect(page.getByRole("button", { name: /^create image$/i })).toBeEnabled();
    await expect(page.getByRole("img", { name: /generated image for this post/i })).toBeVisible();
  });
});

/**
 * §1A — the whole of visual posting on a manual channel: the asset only has to be
 * downloadable. No X media upload, no LinkedIn registerUpload, no Meta container,
 * no Meta app review. Instagram works end to end here, months before Phase 7.
 */
test.describe("Manual channel: download it and attach it yourself", () => {
  test.beforeEach(async ({ page }) => {
    test.skip(!isClerkConfigured(), "Clerk keys not configured");
    await clerkAuth(page);
  });

  test("offers a Download and says who attaches it", async ({ page }) => {
    test.setTimeout(120_000);
    await stubQueue(page, { manual: true, media: [asset()] });
    await openQueue(page);

    const download = page.getByRole("link", { name: /^download image$/i });
    await expect(download).toBeVisible();
    // A download, not a clipboard write: image-to-clipboard fails silently on too
    // many browsers, and the attribute plus a real href keeps it in the gesture.
    await expect(download).toHaveAttribute("href", IMAGE_URL);
    await expect(download).toHaveAttribute("download", /\.png$/);

    await expect(
      page.getByText(/download the image, then attach it in the composer/i)
    ).toBeVisible();
  });

  test("no copy claims the product attached or published anything", async ({ page }) => {
    test.setTimeout(120_000);
    await stubQueue(page, { manual: true, media: [asset()] });
    await openQueue(page);

    const card = page.locator("article", { hasText: BODY });
    await expect(card).toBeVisible();
    // Product rule 1, on a channel with no tokens: the product posts nothing here,
    // so the word may not appear on the card at all.
    await expect(card.getByText(/\bpublish/i)).toHaveCount(0);
    // And it says plainly who does the attaching.
    await expect(
      card.getByText(/campaignforge doesn't attach it or post it for you/i)
    ).toBeVisible();
    // What it offers instead.
    await expect(card.getByRole("button", { name: /post it yourself/i })).toBeVisible();
    await expect(card.getByRole("link", { name: /^download image$/i })).toBeVisible();
  });
});
