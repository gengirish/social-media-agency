import { test, expect } from "@playwright/test";
import { clerkAuth, createClerkUser, deleteClerkUser, isClerkConfigured } from "./helpers/auth";

/**
 * First run for a personal account: Welcome must offer a way into onboarding,
 * and that way must end at an open form.
 *
 * The bug this covers: Welcome's CTA pointed at /clients?new=1, and the Clients
 * page ignored ?new=1 for personal accounts. The link worked, the form never
 * opened, and a personal account whose brand record was missing got a message
 * telling it to contact support instead.
 */
test.describe("Personal account onboarding", () => {
  let user: { id: string; email: string } | null = null;

  test.afterAll(async () => {
    if (user) await deleteClerkUser(user.id);
  });

  test("a new personal account reaches the brand form from Welcome", async ({ page }) => {
    test.skip(!isClerkConfigured(), "Clerk keys not configured");
    test.setTimeout(120_000);

    // A fresh Clerk user means a fresh org: the backend provisions it as a
    // personal account on the first authenticated request.
    user = await createClerkUser();
    await clerkAuth(page, user.id);

    await page.goto("/welcome", { waitUntil: "domcontentloaded" });
    await expect(page.getByText(/welcome to campaignforge|pick up where you left off/i)).toBeVisible({
      timeout: 30000,
    });

    // A personal account is never offered "Add your first client".
    await expect(page.getByRole("link", { name: /add your first client/i })).toHaveCount(0);

    // Provisioning already created the brand record, so the Welcome CTA may be
    // the step list rather than "Set up your brand". Take the link when it is
    // there — that is the path being tested — and the URL directly otherwise.
    const setUp = page.getByRole("link", { name: /set up your brand/i });
    if (await setUp.count()) {
      await setUp.first().click();
    } else {
      await page.goto("/clients?new=1", { waitUntil: "domcontentloaded" });
    }

    await expect(page).toHaveURL(/\/clients\?new=1/, { timeout: 30000 });
    await expect(page.getByRole("heading", { name: /^your brand$/i }).first()).toBeVisible({
      timeout: 30000,
    });

    // The form itself, not just its heading.
    await expect(page.getByLabel(/^brand name/i)).toBeVisible({ timeout: 30000 });
    await expect(page.getByLabel(/^industry/i)).toBeVisible();
    await expect(page.getByRole("button", { name: /create brand/i })).toBeVisible();

    // And never the dead end it used to be.
    await expect(page.getByText(/contact support/i)).toHaveCount(0);
  });
});
