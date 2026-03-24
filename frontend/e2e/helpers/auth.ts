import { setupClerkTestingToken } from "@clerk/testing/playwright";
import { type Page } from "@playwright/test";

export const API_URL = process.env.API_URL || "https://campaignforge-api.fly.dev";

/** True when real Clerk keys are present. */
export function isClerkConfigured(): boolean {
  const sk = process.env.CLERK_SECRET_KEY ?? "";
  return !!sk && !sk.startsWith("sk_test_xxxxx");
}

/** Authenticate the page via Clerk testing token (bypasses UI sign-in). */
export async function clerkAuth(page: Page) {
  await setupClerkTestingToken({ page });
}
