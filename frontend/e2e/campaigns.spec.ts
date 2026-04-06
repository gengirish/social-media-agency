import { test, expect } from "@playwright/test";
import { clerkAuth, isClerkConfigured } from "./helpers/auth";

test.describe("Campaigns", () => {
  const brandName = `E2E Brand ${Date.now()}`;

  test.beforeEach(async ({ page }) => {
    test.skip(!isClerkConfigured(), "Clerk keys not configured");
    await clerkAuth(page);
  });

  test("wizard creates campaign; detail shows Live Agents and Content", async ({ page }) => {
    test.setTimeout(120_000);
    const campaignTitle = `E2E Campaign ${Date.now()}`;

    await page.goto("/clients", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: /^clients$/i })).toBeVisible({ timeout: 20000 });
    await page.getByRole("button", { name: /add client/i }).click();
    await page.getByLabel(/^brand name/i).fill(brandName);
    await page.getByLabel(/^industry/i).fill("SaaS");

    const clientResponse = page.waitForResponse(
      (r) => r.url().includes("/clients") && r.request().method() === "POST",
      { timeout: 30000 }
    );
    await page.getByRole("button", { name: /create client/i }).click();
    await clientResponse;
    await expect(page.getByText(brandName, { exact: true })).toBeVisible({ timeout: 30000 });

    await page.goto("/campaigns/new", { waitUntil: "domcontentloaded" });
    await expect(page.getByText(/step 1 of 3/i)).toBeVisible({ timeout: 20000 });
    await page.locator("select").first().selectOption({ label: `${brandName} — SaaS` });

    await page.getByPlaceholder("Q2 Product Launch Campaign").fill(campaignTitle);
    await page
      .getByPlaceholder(/Increase brand awareness/i)
      .fill("Drive sign-ups for the new product line during Q2.");

    await page.getByRole("button", { name: /^next$/i }).click();
    await expect(page.getByText(/step 2 of 3/i)).toBeVisible();

    await page.getByRole("button", { name: /^next$/i }).click();
    await expect(page.getByText(/step 3 of 3/i)).toBeVisible();

    await page.getByRole("button", { name: /launch campaign/i }).click();
    await expect(page).toHaveURL(/\/campaigns\/[^/]+/, { timeout: 60000 });

    await expect(page.getByRole("heading", { name: campaignTitle })).toBeVisible({ timeout: 20000 });
    await expect(page.getByRole("button", { name: /live agents/i })).toBeVisible({ timeout: 10000 });
    await expect(page.getByRole("button", { name: /content/i })).toBeVisible({ timeout: 10000 });

    await page.goto("/campaigns", { waitUntil: "domcontentloaded" });
    await page.locator(`a[href^="/campaigns/"]`).filter({ hasText: campaignTitle }).first().click({ timeout: 20000 });
    await expect(page).toHaveURL(/\/campaigns\/[^/]+/, { timeout: 20000 });
    await expect(page.getByRole("button", { name: /live agents/i })).toBeVisible({ timeout: 20000 });
    await expect(page.getByRole("button", { name: /content/i })).toBeVisible({ timeout: 10000 });
  });
});
