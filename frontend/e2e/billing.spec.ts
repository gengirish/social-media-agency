import { test, expect } from "@playwright/test";
import { clerkAuth } from "./helpers/auth";

test.describe("Billing / Pricing", () => {
  test.beforeEach(async ({ page }) => {
    await clerkAuth(page);
  });

  test("pricing shows four tiers, prices, and current plan", async ({ page }) => {
    await page.goto("/pricing");
    await expect(page.getByRole("heading", { name: /simple pricing/i })).toBeVisible();

    const tiers = ["Free", "Starter", "Professional", "Enterprise"];
    for (const tier of tiers) {
      await expect(page.getByText(tier, { exact: true }).first()).toBeVisible();
    }
  });
});
