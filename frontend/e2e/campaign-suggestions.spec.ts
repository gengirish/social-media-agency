import { test, expect, type Page } from "@playwright/test";
import { clerkAuth, isClerkConfigured } from "./helpers/auth";

/**
 * "Suggest campaigns" on New Campaign's Brief step.
 *
 * The API is stubbed: a live run would spend a real generation and depend on an
 * LLM. What is under test is the wizard's side — the request it sends, that
 * "Use this" copies a suggestion into the form without touching the budget,
 * and that a 409 `brand_profile_required` points at Setup › Profile.
 *
 * NOT covered here (needs a backend fixture): the server's own validation (422
 * dates, 502 unusable output, 402 quota) and the generation charge.
 */

const ORG_ID = "00000000-0000-0000-0000-0000000000a3";
const CLIENT_ID = "00000000-0000-0000-0000-0000000000b3";

const SUGGESTIONS = [
  {
    angle: "launch_offer",
    campaign_name: "Spring Starter Week",
    objective: "Introduce the new starter plan to small teams who have not tried the product yet.",
    target_audience: "Founders of 5–20 person teams",
    key_messages: ["Set up in an afternoon", "Starter plan for small teams"],
    channels: ["linkedin", "instagram"],
    start_date: "2026-12-01",
    end_date: "2026-12-30",
    additional_context: "Keep the tone practical; do not mention competitors.",
    rationale: "The brand profile lists small teams as the primary audience.",
  },
  {
    angle: "thought_leadership",
    campaign_name: "Lessons From the Field",
    objective: "Share what the team has learned about onboarding so prospects see the expertise behind it.",
    target_audience: "Operations leads",
    key_messages: ["Onboarding is a process, not a form"],
    channels: ["linkedin"],
    start_date: "2026-12-01",
    end_date: "2026-12-30",
    additional_context: "",
    rationale: "The differentiator is the team's onboarding expertise.",
  },
  {
    angle: "community",
    campaign_name: "Customer Corner",
    objective: "Invite existing customers to share how they use the product, and feature their stories.",
    target_audience: "Existing customers",
    key_messages: ["Your setup, in your words"],
    channels: ["facebook", "twitter"],
    start_date: "2026-12-01",
    end_date: "2026-12-30",
    additional_context: "Ask permission before featuring anyone.",
    rationale: "Community posts suit the brand's friendly tone register.",
  },
];

function json(body: unknown, status = 200) {
  return { status, contentType: "application/json", body: JSON.stringify(body) };
}

interface StubOptions {
  /** Answer the suggestions call with this status and detail instead of 200. */
  fail?: { status: number; detail: unknown };
}

async function stubWizard(page: Page, options: StubOptions = {}) {
  const state = { suggestionCalls: [] as Record<string, unknown>[], createCalls: 0 };

  await page.route("**/api/v1/auth/me", (route) =>
    route.fulfill(
      json({
        user_id: "00000000-0000-0000-0000-0000000000d3",
        email: "e2e@example.com",
        role: "owner",
        org_id: ORG_ID,
        account_type: "business",
        capabilities: ["read", "campaign.run", "content.approve", "publish.write", "billing.manage"],
      })
    )
  );

  await page.route("**/api/v1/clients/overview", (route) =>
    route.fulfill(
      json({
        items: [
          {
            id: CLIENT_ID,
            brand_name: "Suggest Co",
            website_url: null,
            has_brand_profile: options.fail?.status !== 409,
            connected_accounts: 0,
            total_posts: 0,
            pending: 0,
            approved: 0,
            scheduled: 0,
            published: 0,
            failed: 0,
            campaign_focus: null,
          },
        ],
      })
    )
  );

  // The wizard's client picker reads the plain list.
  await page.route(/\/api\/v1\/clients\?/, (route) =>
    route.fulfill(
      json({
        items: [
          {
            id: CLIENT_ID,
            org_id: ORG_ID,
            brand_name: "Suggest Co",
            industry: "Software",
            description: "",
            website_url: null,
            contact_email: null,
            logo_url: null,
            is_active: true,
            created_at: new Date().toISOString(),
          },
        ],
        total: 1,
        page: 1,
        per_page: 20,
      })
    )
  );

  await page.route("**/api/v1/billing/subscription", (route) =>
    route.fulfill(json({ plan_tier: "starter", posts_limit: 200, posts_used: 0, generations_limit: 100, generations_used: 4 }))
  );

  await page.route("**/api/v1/campaigns/suggestions", (route) => {
    state.suggestionCalls.push((route.request().postDataJSON() ?? {}) as Record<string, unknown>);
    if (options.fail) return route.fulfill(json({ detail: options.fail.detail }, options.fail.status));
    return route.fulfill(
      json({
        client_id: CLIENT_ID,
        window: { start_date: "2026-12-01", end_date: "2026-12-30" },
        suggestions: SUGGESTIONS,
      })
    );
  });

  // Nothing in these tests may create a campaign.
  await page.route(/\/api\/v1\/campaigns$/, (route) => {
    if (route.request().method() === "POST") state.createCalls += 1;
    return route.fulfill(json({ items: [], total: 0, page: 1, per_page: 20 }));
  });

  return state;
}

async function openWizard(page: Page) {
  await page.goto("/campaigns/new", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: /^new campaign$/i })).toBeVisible({ timeout: 30000 });
  await page.locator("#campaign-client").selectOption(CLIENT_ID);
}

test.describe("Suggest campaigns (New Campaign)", () => {
  test.beforeEach(async ({ page }) => {
    test.skip(!isClerkConfigured(), "Clerk keys not configured");
    await clerkAuth(page);
  });

  test("suggests three campaigns and Use this fills the brief, not the budget", async ({ page }) => {
    test.setTimeout(120_000);
    const state = await stubWizard(page);
    await openWizard(page);

    await expect(page.getByText(/uses 1 generation/i)).toBeVisible();
    await page.locator("#campaign-suggest-hint").fill("launching v2 in December");
    await page.getByRole("button", { name: /suggest campaigns/i }).click();

    const cards = page.getByTestId("campaign-suggestion");
    await expect(cards).toHaveCount(3, { timeout: 15000 });
    await expect(cards.first()).toContainText("Launch or offer");
    await expect(cards.first()).toContainText("Why this one");

    expect(state.suggestionCalls).toHaveLength(1);
    expect(state.suggestionCalls[0]).toMatchObject({ client_id: CLIENT_ID, hint: "launching v2 in December" });
    // No dates were set on the form, so none are sent.
    expect(state.suggestionCalls[0]).not.toHaveProperty("start_date");
    expect(state.suggestionCalls[0]).not.toHaveProperty("end_date");

    await page.getByRole("button", { name: "Use this: Spring Starter Week" }).click();

    await expect(page.locator("#campaign-name")).toHaveValue("Spring Starter Week");
    await expect(page.locator("#campaign-objective")).toHaveValue(SUGGESTIONS[0].objective);
    await expect(page.locator("#campaign-audience")).toHaveValue(SUGGESTIONS[0].target_audience);
    await expect(page.locator("#campaign-messages")).toHaveValue(SUGGESTIONS[0].key_messages.join("\n"));
    await expect(page.getByTestId("suggestion-note")).toContainText("Spring Starter Week");

    await page.getByRole("button", { name: /^next/i }).click();

    // Channels replaced by the suggestion's organic pair; the default X tick is gone.
    await expect(page.getByRole("button", { name: /linkedin/i }).first()).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("button", { name: /instagram/i })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("button", { name: /x \/ twitter/i })).toHaveAttribute("aria-pressed", "false");
    // Paid ads and budget are a spend decision — never filled.
    await expect(page.getByRole("button", { name: /google ads/i })).toHaveAttribute("aria-pressed", "false");
    await expect(page.locator("#campaign-budget")).toHaveValue("");
    await expect(page.locator("#campaign-start")).toHaveValue("2026-12-01");
    await expect(page.locator("#campaign-end")).toHaveValue("2026-12-30");
    await expect(page.locator("#campaign-context")).toHaveValue(SUGGESTIONS[0].additional_context);

    expect(state.createCalls).toBe(0);
  });

  test("asks before overwriting a brief the user has typed", async ({ page }) => {
    test.setTimeout(120_000);
    await stubWizard(page);
    await openWizard(page);

    await page.locator("#campaign-name").fill("My own name");
    await page.getByRole("button", { name: /suggest campaigns/i }).click();
    await expect(page.getByTestId("campaign-suggestion")).toHaveCount(3, { timeout: 15000 });

    await page.getByRole("button", { name: "Use this: Customer Corner" }).click();
    await page.getByRole("button", { name: /keep mine/i }).click();
    await expect(page.locator("#campaign-name")).toHaveValue("My own name");

    await page.getByRole("button", { name: "Use this: Customer Corner" }).click();
    await page.getByRole("button", { name: /^replace$/i }).click();
    await expect(page.locator("#campaign-name")).toHaveValue("Customer Corner");
  });

  test("409 brand_profile_required links to Setup › Profile", async ({ page }) => {
    test.setTimeout(120_000);
    await stubWizard(page, {
      fail: {
        status: 409,
        detail: { code: "brand_profile_required", message: "Set up this client's brand profile first." },
      },
    });
    await openWizard(page);

    await page.getByRole("button", { name: /suggest campaigns/i }).click();
    const link = page.getByRole("link", { name: /set up the brand profile/i });
    await expect(link).toBeVisible({ timeout: 15000 });
    await expect(link).toHaveAttribute("href", "/setup/profile");
    await expect(page.getByTestId("campaign-suggestion")).toHaveCount(0);
  });
});
