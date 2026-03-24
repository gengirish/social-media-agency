import { test, expect } from "@playwright/test";
import { clerkAuth } from "./helpers/auth";

test.describe("Clients", () => {
  test.beforeEach(async ({ page }) => {
    await clerkAuth(page);
  });

  test("create client and see it in the list", async ({ page }) => {
    const brand = `E2E Client ${Date.now()}`;

    await page.goto("/clients");
    await expect(page.getByRole("heading", { name: /^clients$/i })).toBeVisible();

    await page.getByRole("button", { name: /add client/i }).click();
    await expect(page.getByRole("heading", { name: /^new client$/i })).toBeVisible();

    await page.getByLabel(/^brand name/i).fill(brand);
    await page.getByLabel(/^industry/i).fill("Technology");
    await page.getByLabel(/^description/i).fill("E2E generated client for Playwright.");

    await page.getByRole("button", { name: /create client/i }).click();

    await expect(page.getByText(brand, { exact: true })).toBeVisible({ timeout: 20000 });
  });
});
