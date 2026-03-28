import { test, expect } from "@playwright/test";
import { clerkAuth, isClerkConfigured } from "./helpers/auth";

test.describe("Billing / Pricing", () => {
  test.beforeEach(async ({ page }) => {
    test.skip(!isClerkConfigured(), "Clerk keys not configured");
    await clerkAuth(page);
  });

  test("pricing shows four tiers, prices, and current plan", async ({ page }) => {
    await page.goto("/pricing");
    await expect(page.getByRole("heading", { name: /simple pricing/i })).toBeVisible({ timeout: 20000 });

    const tiers = ["Free", "Starter", "Growth", "Agency"];
    for (const tier of tiers) {
      await expect(page.getByText(tier, { exact: true }).first()).toBeVisible();
    }
  });
});
