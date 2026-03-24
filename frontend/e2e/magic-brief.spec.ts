import { test, expect } from "@playwright/test";
import { clerkAuth } from "./helpers/auth";

test.describe("Magic Brief", () => {
  test.beforeEach(async ({ page }) => {
    await clerkAuth(page);
  });

  test("scan website produces brand profile", async ({ page }) => {
    test.setTimeout(180000);

    await page.goto("/campaigns/new/magic-brief");
    await expect(page.getByRole("heading", { name: /^magic brief$/i })).toBeVisible();

    const urlInput = page.getByPlaceholder("https://acme.com").or(page.locator('input[type="text"]').first());
    await urlInput.fill("https://example.com");

    await page.getByRole("button", { name: /scan website/i }).click();

    await expect(page.getByText(/brand profile/i).first()).toBeVisible({ timeout: 120000 });
    await expect(page.getByRole("heading", { level: 2 }).first()).toBeVisible();
  });
});
