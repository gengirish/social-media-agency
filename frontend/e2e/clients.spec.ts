import { test, expect } from "@playwright/test";
import { clerkAuth, isClerkConfigured } from "./helpers/auth";

test.describe("Clients", () => {
  test.beforeEach(async ({ page }) => {
    test.skip(!isClerkConfigured(), "Clerk keys not configured");
    await clerkAuth(page);
  });

  test("create client and see it in the list", async ({ page }) => {
    test.setTimeout(120_000);
    const brand = `E2E Client ${Date.now()}`;

    await page.goto("/clients", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: /^clients$/i })).toBeVisible({ timeout: 20000 });

    await page.getByRole("button", { name: /add client/i }).click();
    await expect(page.getByRole("heading", { name: /^new client$/i })).toBeVisible({ timeout: 10000 });

    await page.getByLabel(/^brand name/i).fill(brand);
    await page.getByLabel(/^industry/i).fill("Technology");
    await page.getByLabel(/^description/i).fill("E2E generated client for Playwright.");

    const responsePromise = page.waitForResponse(
      (r) => r.url().includes("/clients") && r.request().method() === "POST",
      { timeout: 30000 }
    );
    await page.getByRole("button", { name: /create client/i }).click();
    await responsePromise;

    await expect(page.getByText(brand, { exact: true })).toBeVisible({ timeout: 30000 });
  });
});
