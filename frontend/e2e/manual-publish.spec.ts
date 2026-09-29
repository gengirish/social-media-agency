import { test, expect, type Page } from "@playwright/test";
import { clerkAuth, isClerkConfigured } from "./helpers/auth";

/**
 * "Post it yourself" — the Queue flow for a channel with no OAuth tokens
 * (docs/manual-publish-plan-260929.md, Phase 3).
 *
 * The API is stubbed rather than seeded. A manual channel is a `platform_account`
 * row with `status = "manual"`, and there is no way to create one from the Queue —
 * it needs Setup › Accounts and an `oauth.connect` holder — so a live-data version
 * of this spec would have to register a real page on a real client and then leave
 * it behind. The stubs cover exactly the reads the Queue makes, so what is under
 * test is the card's own behaviour: which controls it offers, that Cancel writes
 * nothing, and that confirm calls `mark-posted` once and moves the post on.
 *
 * Phase 5 adds the other half: a piece that was posted by hand and has no link on
 * file. It must read as "no link, metrics unavailable" rather than as a zero, and
 * offer a permanent "Add link" that PATCHes `post-url`.
 *
 * NOT covered here (needs a backend fixture): the server's own refusals — 400 with
 * no manual channel or an unsafe link, 402 on an exhausted plan, 409 on an unapproved
 * piece, 409 `not_published` on the post-URL patch — and the quota pre-check, which
 * depends on a real `posts_used`.
 */

const ORG_ID = "00000000-0000-0000-0000-0000000000a1";
const CLIENT_ID = "00000000-0000-0000-0000-0000000000b1";
const POST_ID = "00000000-0000-0000-0000-0000000000c1";
const BODY = "Three weeks of onboarding, cut to one afternoon. Here is what we removed.";
const LINK = "https://www.linkedin.com/feed/update/urn:li:share:7000000000000000000/";
/** A reminder already on file, far enough out that the card never renders it as overdue. */
const REMINDER_AT = new Date(Date.now() + 36 * 60 * 60 * 1000).toISOString();

function post(status: string, postUrl: string | null = null, scheduledAt: string | null = null) {
  return {
    id: POST_ID,
    campaign_id: null,
    client_id: CLIENT_ID,
    content_type: "social_post",
    platform: "linkedin",
    title: "Onboarding, cut down",
    body: BODY,
    hashtags: ["onboarding"],
    status,
    ai_generated: true,
    performance_score: null,
    created_at: new Date().toISOString(),
    scheduled_at: scheduledAt,
    published_at: status === "published" ? new Date().toISOString() : null,
    metadata_: status === "published" ? { publish_mode: "manual", post_url: postUrl } : {},
  };
}

function json(body: unknown) {
  return { status: 200, contentType: "application/json", body: JSON.stringify(body) };
}

/**
 * Every read the Queue makes, with one piece of mutable state: `posted`, which
 * flips when `mark-posted` is called, so the list reloads the way the real API
 * would answer after it.
 */
interface StubOptions {
  /**
   * Which status the single post starts in. Default `"approved"` (Phase 3's flow).
   * `"scheduled"` is Phase 4's reminder already set — the state a reschedule starts from.
   */
  start?: "approved" | "scheduled" | "published";
  /** A link already on file for a published post. `null` is the Phase 5 case. */
  postUrl?: string | null;
}

async function stubQueue(page: Page, options: StubOptions = {}) {
  const state = {
    posted: options.start === "published",
    markPostedCalls: 0,
    /** Every ISO time the Queue sent to `POST /publishing/{id}/schedule`, in order. */
    scheduleCalls: [] as (string | null)[],
    postUrl: options.postUrl ?? null,
    /** Every `post_url` the Queue PATCHed, in order — so "once, with what was typed" is checkable. */
    postUrlCalls: [] as (string | null)[],
  };

  await page.route("**/api/v1/auth/me", (route) =>
    route.fulfill(
      json({
        user_id: "00000000-0000-0000-0000-0000000000d1",
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
            pending: 0,
            approved: state.posted || options.start === "scheduled" ? 0 : 1,
            scheduled: options.start === "scheduled" && !state.posted ? 1 : 0,
            published: state.posted ? 1 : 0,
            failed: 0,
            campaign_focus: null,
          },
        ],
      })
    )
  );

  await page.route("**/api/v1/billing/subscription", (route) =>
    route.fulfill(json({ plan_tier: "starter", posts_limit: 200, posts_used: 3, generations_limit: 100, generations_used: 4 }))
  );

  await page.route("**/api/v1/post-studio/channels*", (route) =>
    route.fulfill(json({ connected: [], supported: ["linkedin", "twitter", "facebook", "instagram"] }))
  );

  await page.route("**/api/v1/clients/*/brand-profile", (route) =>
    route.fulfill(json({ client_id: CLIENT_ID, brand_name: "Manual Co" }))
  );

  // The LinkedIn page is registered by hand: no tokens, so nothing publishes to it.
  await page.route("**/api/v1/setup/*/accounts", (route) => {
    if (new URL(route.request().url()).pathname.endsWith("/accounts")) {
      return route.fulfill(
        json({
          accounts: [
            {
              id: "00000000-0000-0000-0000-0000000000e1",
              platform: "linkedin",
              account_handle: "manual-co",
              display_name: "Manual Co",
              status: "manual",
              profile_url: null,
              connected_at: null,
            },
          ],
          oauth: {},
        })
      );
    }
    return route.continue();
  });

  await page.route("**/api/v1/content?**", (route) => {
    const params = new URL(route.request().url()).searchParams;
    const wanted = params.get("content_status");
    const current = state.posted ? "published" : options.start === "scheduled" ? "scheduled" : "approved";
    const items =
      wanted === current ? [post(current, state.postUrl, current === "scheduled" ? REMINDER_AT : null)] : [];
    return route.fulfill(json({ items, total: items.length, page: 1, per_page: Number(params.get("per_page") ?? 50) }));
  });

  /*
   * The reminder. Same endpoint a connected post is scheduled with — Phase 4 lifted
   * `ensure_schedulable`'s refusal for a manual channel rather than adding a second
   * route — so what is under test here is purely that the UI calls it, once, and never
   * describes it as publishing.
   */
  await page.route("**/api/v1/publishing/*/schedule", (route) => {
    const body = (route.request().postDataJSON() ?? {}) as { scheduled_at?: string };
    state.scheduleCalls.push(body.scheduled_at ?? null);
    return route.fulfill(json({ content_id: POST_ID, status: "scheduled", scheduled_at: body.scheduled_at ?? null }));
  });

  await page.route("**/api/v1/publishing/*/mark-posted", (route) => {
    state.markPostedCalls += 1;
    state.posted = true;
    return route.fulfill(
      json({ status: "published", content_id: POST_ID, publish_mode: "manual", post_url: null })
    );
  });

  // Phase 5: the link attached after the fact. Only `post_url` changes — the piece
  // stays `published`, which is why the card updates in place instead of reloading.
  await page.route("**/api/v1/publishing/*/post-url", (route) => {
    const body = (route.request().postDataJSON() ?? {}) as { post_url?: string | null };
    state.postUrlCalls.push(body.post_url ?? null);
    state.postUrl = body.post_url ?? null;
    return route.fulfill(json({ content_id: POST_ID, post_url: state.postUrl }));
  });

  return state;
}

test.describe("Post it yourself (manual channel)", () => {
  test.beforeEach(async ({ page, context }) => {
    test.skip(!isClerkConfigured(), "Clerk keys not configured");
    await context.grantPermissions(["clipboard-read", "clipboard-write"]).catch(() => {
      // Chromium only; the flow still works, the clipboard write just fails softly.
    });
    await clerkAuth(page);
  });

  async function openApproved(page: Page) {
    await page.goto("/content", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: /^queue$/i })).toBeVisible({ timeout: 30000 });
    await page.getByRole("tab", { name: /approved/i }).click();
    await expect(page.getByText(BODY)).toBeVisible({ timeout: 30000 });
  }

  test("offers Post it yourself and never Publish now", async ({ page }) => {
    test.setTimeout(120_000);
    await stubQueue(page);
    await openApproved(page);

    await expect(page.getByRole("button", { name: /post it yourself/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /^publish now$/i })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /^schedule$/i })).toHaveCount(0);
  });

  test("Cancel leaves the post in Approved and records nothing", async ({ page }) => {
    test.setTimeout(120_000);
    const state = await stubQueue(page);
    await openApproved(page);

    const popup = page.waitForEvent("popup", { timeout: 15000 }).catch(() => null);
    await page.getByRole("button", { name: /post it yourself/i }).click();
    const tab = await popup;
    if (tab) await tab.close().catch(() => undefined);

    // LinkedIn does not take post text in a URL, so the copy must say so.
    await expect(page.getByText(/paste it into the linkedin composer/i)).toBeVisible();
    await page.getByRole("button", { name: /^cancel$/i }).click();

    await expect(page.getByRole("button", { name: /post it yourself/i })).toBeVisible();
    expect(state.markPostedCalls).toBe(0);
    // Still where it was: Approved, not Published.
    await expect(page.getByText(BODY)).toBeVisible();
  });

  test("I posted it records it once and moves it to Published", async ({ page }) => {
    test.setTimeout(120_000);
    const state = await stubQueue(page);
    await openApproved(page);

    const popup = page.waitForEvent("popup", { timeout: 15000 }).catch(() => null);
    await page.getByRole("button", { name: /post it yourself/i }).click();
    const tab = await popup;
    if (tab) await tab.close().catch(() => undefined);

    await page.getByRole("button", { name: /i posted it/i }).click();

    // The Approved tab empties …
    await expect(page.getByText(BODY)).toHaveCount(0, { timeout: 30000 });
    expect(state.markPostedCalls).toBe(1);

    // … and the post is in Published, described as posted by hand, not published by us.
    await page.getByRole("tab", { name: /published/i }).click();
    await expect(page.getByText(BODY)).toBeVisible({ timeout: 30000 });
    await expect(page.getByText(/posted by hand/i)).toBeVisible();
  });
});

/**
 * Phase 5 — the link that arrives later, and the honest state until it does.
 *
 * The permanence is the point: a post recorded from a phone may only get its link
 * days afterwards, so "Add link" is not a one-time prompt and is present on every
 * visit until a link is actually on file.
 */
test.describe("Published by hand with no link (Phase 5)", () => {
  test.beforeEach(async ({ page }) => {
    test.skip(!isClerkConfigured(), "Clerk keys not configured");
    await clerkAuth(page);
  });

  async function openPublished(page: Page) {
    await page.goto("/content", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: /^queue$/i })).toBeVisible({ timeout: 30000 });
    await page.getByRole("tab", { name: /published/i }).click();
    await expect(page.getByText(BODY)).toBeVisible({ timeout: 30000 });
  }

  test("says metrics are unavailable and saves the link that was typed", async ({ page }) => {
    test.setTimeout(120_000);
    const state = await stubQueue(page, { start: "published" });
    await openPublished(page);

    // Product rule 4: the absent metric is named, never rendered as a zero.
    await expect(page.getByText(/posted manually — no link, metrics unavailable/i)).toBeVisible();
    await expect(page.getByRole("link", { name: /view post/i })).toHaveCount(0);

    await page.getByRole("button", { name: /^add link$/i }).click();
    await page.getByLabel(/^link to the post$/i).fill(LINK);
    await page.getByRole("button", { name: /save link/i }).click();

    // Updated in place: the card gains the link and loses the empty state.
    await expect(page.getByRole("link", { name: /view post/i })).toBeVisible({ timeout: 30000 });
    await expect(page.getByText(/metrics unavailable/i)).toHaveCount(0);
    expect(state.postUrlCalls).toEqual([LINK]);
  });

  test("offers no Add link once a link is on file", async ({ page }) => {
    test.setTimeout(120_000);
    const state = await stubQueue(page, { start: "published", postUrl: LINK });
    await openPublished(page);

    await expect(page.getByRole("link", { name: /view post/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /^add link$/i })).toHaveCount(0);
    await expect(page.getByText(/metrics unavailable/i)).toHaveCount(0);
    expect(state.postUrlCalls).toEqual([]);
  });
});

/**
 * Phase 4's other half — "Schedule as a reminder".
 *
 * The backend already accepted a scheduled manual piece (`ensure_schedulable` lifts its
 * refusal for a manual channel, which is also why Instagram and TikTok are schedulable
 * there) and the card already worded a scheduled manual piece as "Reminder around
 * <time>". Nothing offered it, so none of that was reachable. These cover the button,
 * the honesty of the dialog, and that confirming hits the schedule endpoint exactly once.
 *
 * The one thing worth stating about the copy: the dialog must not contain the word
 * "publish" at all for a manual channel. It is the same dialog a connected post uses,
 * where "CampaignForge publishes to … live, connected account" is true and important —
 * so the branch is exactly the kind of thing a later edit re-merges by accident.
 *
 * NOT covered (needs a backend fixture): the 403 a `member` gets from the schedule
 * endpoint. The button is hidden for them client-side, so there is nothing to click.
 */
test.describe("Schedule a manual post as a reminder (Phase 4)", () => {
  test.beforeEach(async ({ page }) => {
    test.skip(!isClerkConfigured(), "Clerk keys not configured");
    await clerkAuth(page);
  });

  async function openTab(page: Page, tab: RegExp) {
    await page.goto("/content", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: /^queue$/i })).toBeVisible({ timeout: 30000 });
    await page.getByRole("tab", { name: tab }).click();
    await expect(page.getByText(BODY)).toBeVisible({ timeout: 30000 });
  }

  test("offers it beside Post it yourself, and still no Publish now", async ({ page }) => {
    test.setTimeout(120_000);
    await stubQueue(page);
    await openTab(page, /approved/i);

    await expect(page.getByRole("button", { name: /post it yourself/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /schedule as a reminder/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /^publish now$/i })).toHaveCount(0);
  });

  test("the dialog never says the product will publish it", async ({ page }) => {
    test.setTimeout(120_000);
    const state = await stubQueue(page);
    await openTab(page, /approved/i);
    await page.getByRole("button", { name: /schedule as a reminder/i }).click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText(/set a reminder to post it yourself/i)).toBeVisible();
    await expect(dialog.getByText(/nothing goes out at this time/i)).toBeVisible();
    // The wake interval is capped at an hour, so the copy may not promise the minute.
    await expect(dialog.getByText(/up to an hour late/i)).toBeVisible();
    // Product rule 1: not "publishes", not "goes live", not anywhere in this dialog.
    await expect(dialog.getByText(/publish/i)).toHaveCount(0);
    await expect(dialog.getByRole("button", { name: /^set reminder$/i })).toBeVisible();

    // Backing out writes nothing, the same as Cancel on the connected dialog.
    await dialog.getByRole("button", { name: /^cancel$/i }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    expect(state.scheduleCalls).toEqual([]);
  });

  test("confirming calls the schedule endpoint once", async ({ page }) => {
    test.setTimeout(120_000);
    const state = await stubQueue(page);
    await openTab(page, /approved/i);
    await page.getByRole("button", { name: /schedule as a reminder/i }).click();

    const dialog = page.getByRole("dialog");
    // The dialog defaults to the top of the next hour, so it is already valid.
    await dialog.getByRole("button", { name: /^set reminder$/i }).click();

    await expect(page.getByRole("dialog")).toHaveCount(0, { timeout: 30000 });
    expect(state.scheduleCalls).toHaveLength(1);
    expect(state.scheduleCalls[0]).toBeTruthy();
    // The confirmation is a reminder, and an approximate one.
    await expect(page.getByText(/reminder set for around/i)).toBeVisible({ timeout: 30000 });
  });

  test("a reminder already set is moved, not rescheduled", async ({ page }) => {
    test.setTimeout(120_000);
    const state = await stubQueue(page, { start: "scheduled" });
    await openTab(page, /^scheduled/i);

    // Phase 5b's card copy, reachable at last.
    await expect(page.getByText(/reminder around/i)).toBeVisible();
    await page.getByRole("button", { name: /move the reminder/i }).click();

    const dialog = page.getByRole("dialog");
    await expect(dialog.getByText(/move this reminder/i)).toBeVisible();
    await expect(dialog.getByText(/publish/i)).toHaveCount(0);
    await dialog.getByRole("button", { name: /^move reminder$/i }).click();

    await expect(page.getByRole("dialog")).toHaveCount(0, { timeout: 30000 });
    expect(state.scheduleCalls).toHaveLength(1);
    await expect(page.getByText(/reminder moved to around/i)).toBeVisible({ timeout: 30000 });
  });
});

/**
 * Phase 4's reminder digest links to a filtered Queue, so the Queue has to read
 * `?client=` and `?status=` — before Phase 5 it read neither and the notification
 * landed on whatever tab the browser last remembered.
 */
test.describe("Queue deep link", () => {
  test.beforeEach(async ({ page }) => {
    test.skip(!isClerkConfigured(), "Clerk keys not configured");
    await clerkAuth(page);
  });

  test("?status=scheduled selects that tab on load", async ({ page }) => {
    test.setTimeout(120_000);
    await stubQueue(page);
    await page.goto(`/content?client=${CLIENT_ID}&status=scheduled`, { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: /^queue$/i })).toBeVisible({ timeout: 30000 });

    await expect(page.getByRole("tab", { name: /^scheduled/i })).toHaveAttribute("aria-selected", "true", {
      timeout: 30000,
    });
    await expect(page.getByRole("tab", { name: /^pending/i })).toHaveAttribute("aria-selected", "false");
  });

  test("an unknown status is ignored and the default tab stands", async ({ page }) => {
    test.setTimeout(120_000);
    await stubQueue(page);
    await page.goto("/content?status=nonsense", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: /^queue$/i })).toBeVisible({ timeout: 30000 });

    await expect(page.getByRole("tab", { name: /^pending/i })).toHaveAttribute("aria-selected", "true", {
      timeout: 30000,
    });
  });
});
