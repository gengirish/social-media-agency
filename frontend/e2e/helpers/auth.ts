import { expect, type APIRequestContext, type Page } from "@playwright/test";

/** Backend base URL for API-only helpers (signup). Browser still uses NEXT_PUBLIC_API_URL from the app build. */
export const API_URL = process.env.API_URL || "https://campaignforge-api.fly.dev";

export type TestUser = {
  email: string;
  password: string;
  name: string;
  org: string;
};

/** Unique user per call — safe for parallel workers. */
export function buildTestUser(): TestUser {
  const id = `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  return {
    email: `e2e-${id}@campaignforge.test`,
    password: "TestPassword123!",
    name: "E2E Tester",
    org: "E2E Test Org",
  };
}

/** Static credentials template (email is fixed at module load). Prefer `buildTestUser()` in tests. */
export const TEST_USER = {
  email: `e2e-test-${Date.now()}@campaignforge.test`,
  password: "TestPassword123!",
  name: "E2E Tester",
  org: "E2E Test Org",
};

/** Register via API so non-auth specs can log in through the UI quickly. */
export async function signupViaApi(request: APIRequestContext, user: TestUser): Promise<void> {
  const res = await request.post(`${API_URL}/api/v1/auth/signup`, {
    data: {
      email: user.email,
      password: user.password,
      full_name: user.name,
      org_name: user.org,
    },
  });
  if (!res.ok()) {
    const body = await res.text();
    throw new Error(`API signup failed ${res.status()}: ${body}`);
  }
}

export async function loginAs(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page).toHaveURL(/\/campaigns/, { timeout: 25000 });
}

export async function logoutIfPossible(page: Page) {
  const signOut = page.getByRole("button", { name: /sign out/i });
  if (await signOut.isVisible().catch(() => false)) {
    await signOut.click();
    await expect(page).toHaveURL(/\/login/, { timeout: 15000 });
  }
}
