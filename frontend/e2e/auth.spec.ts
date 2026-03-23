import { test, expect } from "@playwright/test";
import { buildTestUser, loginAs, logoutIfPossible } from "./helpers/auth";

test.describe("Authentication", () => {
  test.describe("signup → logout → login", () => {
    test.describe.configure({ mode: "serial" });

    test("full account lifecycle", async ({ page }) => {
      const user = buildTestUser();

      await page.goto("/signup");
      await expect(page.getByRole("heading", { name: /create your account/i })).toBeVisible();

      await page.getByLabel("Full Name", { exact: true }).fill(user.name);
      await page.getByLabel("Email", { exact: true }).fill(user.email);
      await page.getByLabel("Password", { exact: true }).fill(user.password);
      await page.getByLabel("Organization Name", { exact: true }).fill(user.org);

      await page.getByRole("button", { name: /create account/i }).click();
      await expect(page).toHaveURL(/\/campaigns/, { timeout: 30000 });

      await logoutIfPossible(page);

      await loginAs(page, user.email, user.password);
      await expect(page.getByRole("heading", { name: /^campaigns$/i })).toBeVisible();
    });
  });

  test("invalid login shows feedback", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Email", { exact: true }).fill("definitely-not-a-user@campaignforge.test");
    await page.getByLabel("Password", { exact: true }).fill("WrongPassword999!");
    await page.getByRole("button", { name: /sign in/i }).click();

    await expect(page).toHaveURL(/\/login/);
    await expect(page.getByRole("heading", { name: /welcome back/i })).toBeVisible();

    const toast = page.locator("[data-sonner-toast]").first();
    await expect(toast).toBeVisible({ timeout: 15000 });
  });
});
