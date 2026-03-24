import { setupClerkTestingToken } from "@clerk/testing/playwright";
import { type Page } from "@playwright/test";

export const API_URL = process.env.API_URL || "https://campaignforge-api.fly.dev";

/** Authenticate the page via Clerk testing token (bypasses UI sign-in). */
export async function clerkAuth(page: Page) {
  await setupClerkTestingToken({ page });
}
