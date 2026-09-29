import { setupClerkTestingToken } from "@clerk/testing/playwright";
import { type Page } from "@playwright/test";

export const API_URL = process.env.API_URL || "https://campaignforge-api.fly.dev";

/** True when real Clerk keys are present. */
export function isClerkConfigured(): boolean {
  const sk = process.env.CLERK_SECRET_KEY ?? "";
  return !!sk && !sk.startsWith("sk_test_xxxxx");
}

async function clerkUserIdForEmail(email: string): Promise<string> {
  const sk = process.env.CLERK_SECRET_KEY!;
  const usersResp = await fetch(
    `https://api.clerk.com/v1/users?email_address=${encodeURIComponent(email)}`,
    { headers: { Authorization: `Bearer ${sk}` } }
  );
  const users = await usersResp.json();
  const userId = users[0]?.id;
  if (!userId) throw new Error(`No Clerk user found for ${email}`);
  return userId;
}

async function createSignInToken(clerkUserId?: string): Promise<string> {
  const sk = process.env.CLERK_SECRET_KEY!;
  const userId = clerkUserId ?? (await clerkUserIdForEmail(process.env.E2E_CLERK_USER_EMAIL!));

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

/**
 * Minimal shape of the Clerk object attached to `window` by @clerk/nextjs.
 * Only the members this helper touches are declared.
 */
type ClerkWindow = Window & {
  Clerk?: {
    loaded?: boolean;
    client: {
      signIn: {
        create(params: { strategy: string; ticket: string }): Promise<{
          status: string;
          createdSessionId?: string;
        }>;
      };
    };
    setActive(params: { session: string }): Promise<void>;
  };
};

/**
 * A brand-new Clerk user, which is how a test gets a brand-new *workspace*: the
 * backend auto-provisions the org, its free subscription and — for a personal
 * account — its one brand record the first time that user is resolved. There is
 * no other way to reach the first-run state; the shared E2E user has long since
 * been through onboarding.
 *
 * Created through the Backend API rather than the sign-up form, because the form
 * demands a verification code from a real mailbox. Caller must `deleteClerkUser`.
 */
export async function createClerkUser(): Promise<{ id: string; email: string }> {
  const sk = process.env.CLERK_SECRET_KEY!;
  const email = `e2e-personal-${Date.now()}@example.com`;

  const resp = await fetch("https://api.clerk.com/v1/users", {
    method: "POST",
    headers: { Authorization: `Bearer ${sk}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      email_address: [email],
      password: `E2e-${Date.now()}-Pw!`,
      first_name: "Solo",
      last_name: "Tester",
      skip_password_checks: true,
    }),
  });
  const body = await resp.json();
  if (!resp.ok || !body.id) {
    throw new Error(`Clerk user create failed (${resp.status}): ${JSON.stringify(body)}`);
  }
  return { id: body.id, email };
}

/** Best-effort teardown — a failure here must not fail the test that passed. */
export async function deleteClerkUser(clerkUserId: string): Promise<void> {
  try {
    await fetch(`https://api.clerk.com/v1/users/${clerkUserId}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${process.env.CLERK_SECRET_KEY!}` },
    });
  } catch {
    // Leaves a test user behind in the Clerk dashboard; nothing else breaks.
  }
}

/** Authenticate via Clerk sign-in token (bypasses MFA). Signs in the shared E2E
 * user unless a specific Clerk user id is given. */
export async function clerkAuth(page: Page, clerkUserId?: string) {
  await setupClerkTestingToken({ page });

  const ticket = await createSignInToken(clerkUserId);

  await page.goto("/sign-in");
  await page.waitForFunction(() => (window as ClerkWindow).Clerk?.loaded, {
    timeout: 15000,
  });

  await page.evaluate(async (t) => {
    const clk = (window as ClerkWindow).Clerk!;
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
