import { setupClerkTestingToken } from "@clerk/testing/playwright";
import { type Page } from "@playwright/test";

export const API_URL = process.env.API_URL || "https://campaignforge-api.fly.dev";

/** True when real Clerk keys are present. */
export function isClerkConfigured(): boolean {
  const sk = process.env.CLERK_SECRET_KEY ?? "";
  return !!sk && !sk.startsWith("sk_test_xxxxx");
}

async function createSignInToken(): Promise<string> {
  const sk = process.env.CLERK_SECRET_KEY!;
  const email = process.env.E2E_CLERK_USER_EMAIL!;

  const usersResp = await fetch(
    `https://api.clerk.com/v1/users?email_address=${encodeURIComponent(email)}`,
    { headers: { Authorization: `Bearer ${sk}` } }
  );
  const users = await usersResp.json();
  const userId = users[0]?.id;
  if (!userId) throw new Error(`No Clerk user found for ${email}`);

  const tokenResp = await fetch("https://api.clerk.com/v1/sign_in_tokens", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${sk}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ user_id: userId }),
  });
  const tokenData = await tokenResp.json();
  return tokenData.token;
}

/** Authenticate via Clerk sign-in token (bypasses MFA). */
export async function clerkAuth(page: Page) {
  await setupClerkTestingToken({ page });

  const ticket = await createSignInToken();

  await page.goto("/sign-in");
  await page.waitForFunction(() => (window as any).Clerk?.loaded, {
    timeout: 15000,
  });

  await page.evaluate(async (t) => {
    const clk = (window as any).Clerk;
    const si = await clk.client.signIn.create({ strategy: "ticket", ticket: t });
    if (si.status === "complete" && si.createdSessionId) {
      await clk.setActive({ session: si.createdSessionId });
    } else {
      throw new Error(`Sign-in incomplete: status=${si.status}`);
    }
  }, ticket);

  await page.goto("/");
  await page.waitForURL((url) => !url.pathname.includes("/sign-in"), {
    timeout: 15000,
  });
}
