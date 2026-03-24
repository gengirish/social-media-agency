import { test, expect } from "@playwright/test";
import { clerkAuth } from "./helpers/auth";

test.describe("Authentication", () => {
  test("unauthenticated user is redirected to sign-in", async ({ page }) => {
    await page.goto("/campaigns");
    await expect(page).toHaveURL(/\/sign-in/, { timeout: 15000 });
  });

  test("authenticated user can access dashboard", async ({ page }) => {
    await clerkAuth(page);
    await page.goto("/campaigns");
    await expect(page.getByRole("heading", { name: /^campaigns$/i })).toBeVisible({ timeout: 20000 });
  });
});
