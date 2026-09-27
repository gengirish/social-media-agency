import { test, expect, type Page } from "@playwright/test";
import { clerkAuth, isClerkConfigured } from "./helpers/auth";

type PageCheck = { path: string; heading: RegExp };

const PAGES: PageCheck[] = [
  { path: "/campaigns", heading: /^campaigns$/i },
  { path: "/clients", heading: /^clients$/i },
  { path: "/content", heading: /^queue$/i },
  { path: "/calendar", heading: /content calendar/i },
  { path: "/team", heading: /^team$/i },
  { path: "/pricing", heading: /simple pricing/i },
  { path: "/settings", heading: /^settings$/i },
  { path: "/analytics", heading: /^analytics$/i },
  { path: "/welcome", heading: /./ },
  { path: "/setup/profile", heading: /^brand profile$/i },
  { path: "/setup/accounts", heading: /^connected accounts$/i },
  { path: "/create/content", heading: /^content$/i },
  { path: "/create/email", heading: /^email$/i },
  { path: "/create/launch", heading: /^launch$/i },
  { path: "/create/ads", heading: /^ads$/i },
  { path: "/inbox", heading: /^inbox$/i },
];

/**
 * Capability-filtered nav (docs/rbac-phase-plan-260923.md, Phase 3A).
 *
 * The E2E user is a single real Clerk identity, so its role is whatever the
 * backend says. To assert the filtering itself, `GET /auth/me` is stubbed:
 * the nav reads nothing else about the viewer, and the stub keeps the test
 * independent of that account's actual role.
 *
 * This is presentation only — the routes stay gated server-side, so a viewer
 * that types /team still gets a 403 from the API.
 */
async function stubMe(page: Page, role: string, capabilities: string[]) {
  await page.route("**/api/v1/auth/me", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        user_id: "00000000-0000-0000-0000-000000000001",
        email: "e2e@example.com",
        role,
        org_id: "00000000-0000-0000-0000-000000000002",
        account_type: "business",
        capabilities,
      }),
    })
  );
}

test.describe("Navigation", () => {
  test.beforeEach(async ({ page }) => {
    test.skip(!isClerkConfigured(), "Clerk keys not configured");
    await clerkAuth(page);
  });

  test("dashboard routes load with primary heading", async ({ page }) => {
    test.setTimeout(120_000);
    for (const { path, heading } of PAGES) {
      await page.goto(path, { waitUntil: "domcontentloaded" });

      await expect(page).toHaveURL(
        new RegExp(`${path.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(/)?(\\?.*)?$`, "i"),
        { timeout: 20000 }
      );

      await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible({
        timeout: 20000,
      });

      await expect(page.getByText(/application error|next\.js.*error/i)).toHaveCount(0);
    }
  });
});

test.describe("Capability-filtered navigation", () => {
  test.beforeEach(async ({ page }) => {
    test.skip(!isClerkConfigured(), "Clerk keys not configured");
    await clerkAuth(page);
  });

  test("a viewer sees no Team or Billing tab", async ({ page }) => {
    await stubMe(page, "viewer", ["read"]);
    await page.goto("/settings", { waitUntil: "domcontentloaded" });

    const nav = page.locator("header");
    await expect(nav.getByRole("link", { name: "Settings", exact: true })).toBeVisible({ timeout: 20000 });
    await expect(nav.getByRole("link", { name: "Team", exact: true })).toHaveCount(0);
    await expect(nav.getByRole("link", { name: "Billing", exact: true })).toHaveCount(0);
  });

  test("an owner sees both", async ({ page }) => {
    await stubMe(page, "owner", [
      "read",
      "campaign.run",
      "content.approve",
      "publish.write",
      "content.override",
      "oauth.connect",
      "team.manage",
      "billing.manage",
    ]);
    await page.goto("/settings", { waitUntil: "domcontentloaded" });

    const nav = page.locator("header");
    await expect(nav.getByRole("link", { name: "Team", exact: true })).toBeVisible({ timeout: 20000 });
    await expect(nav.getByRole("link", { name: "Billing", exact: true })).toBeVisible();
  });
});
