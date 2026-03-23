import { test, expect } from "@playwright/test";
import { buildTestUser, signupViaApi, loginAs } from "./helpers/auth";

test.describe("Billing / Pricing", () => {
  let user: ReturnType<typeof buildTestUser>;

  test.beforeAll(async ({ request }) => {
    user = buildTestUser();
    await signupViaApi(request, user);
  });

  test.beforeEach(async ({ page }) => {
    await loginAs(page, user.email, user.password);
  });

  test("pricing shows four tiers, prices, and current plan", async ({ page }) => {
    await page.goto("/pricing");
    await expect(page.getByRole("heading", { name: /simple pricing/i })).toBeVisible({ timeout: 20000 });

    for (const plan of ["Free", "Starter", "Growth", "Agency"]) {
      await expect(page.getByRole("heading", { name: plan, level: 2 })).toBeVisible();
    }

    await expect(page.getByText(/\$0/).first()).toBeVisible();
    await expect(page.getByText(/\$49/).first()).toBeVisible();
    await expect(page.getByText(/\$149/).first()).toBeVisible();
    await expect(page.getByText(/\$399/).first()).toBeVisible();

    await expect(page.getByText(/current plan/i).first()).toBeVisible();
  });
});
