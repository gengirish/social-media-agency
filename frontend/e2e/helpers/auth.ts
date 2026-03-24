import { setupClerkTestingToken } from "@clerk/testing/playwright";
import { type Page } from "@playwright/test";

export const API_URL = process.env.API_URL || "https://campaignforge-api.fly.dev";

/** True when real Clerk keys are present. */
export function isClerkConfigured(): boolean {
  const sk = process.env.CLERK_SECRET_KEY ?? "";
  return !!sk && !sk.startsWith("sk_test_xxxxx");
}

/** Authenticate the page via Clerk sign-in form. */
export async function clerkAuth(page: Page) {
  await setupClerkTestingToken({ page });

  await page.goto("/sign-in");

  const emailInput = page.getByLabel("Email address");
  await emailInput.waitFor({ state: "visible", timeout: 15000 });
  await emailInput.fill(process.env.E2E_CLERK_USER_EMAIL!);

  const passwordInput = page.getByLabel("Password");
  await passwordInput.fill(process.env.E2E_CLERK_USER_PASSWORD!);

  await page.getByRole("button", { name: /continue/i }).click();

  await page.waitForURL((url) => !url.pathname.includes("/sign-in"), {
    timeout: 15000,
  });
}
