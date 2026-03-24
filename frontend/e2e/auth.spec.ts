import { test, expect } from "@playwright/test";
import { clerkAuth, isClerkConfigured } from "./helpers/auth";

test.describe("Authentication", () => {
  test("sign-in page is accessible", async ({ page }) => {
    test.skip(!isClerkConfigured(), "Clerk keys not configured");
    await page.goto("/sign-in");
    await expect(page).toHaveURL(/\/sign-in/, { timeout: 15000 });
  });

  test("authenticated user can access dashboard", async ({ page }) => {
    test.skip(!isClerkConfigured(), "Clerk keys not configured");
    await clerkAuth(page);
    await page.goto("/campaigns");
    await expect(page.getByRole("heading", { name: /^campaigns$/i })).toBeVisible({ timeout: 20000 });
  });
});
