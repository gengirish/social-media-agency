import { test, expect } from "@playwright/test";
import { clerkAuth, isClerkConfigured } from "./helpers/auth";

type PageCheck = { path: string; heading: RegExp };

const PAGES: PageCheck[] = [
  { path: "/campaigns", heading: /^campaigns$/i },
  { path: "/clients", heading: /^clients$/i },
  { path: "/content", heading: /content library/i },
  { path: "/calendar", heading: /content calendar/i },
  { path: "/team", heading: /^team$/i },
  { path: "/pricing", heading: /simple pricing/i },
  { path: "/settings", heading: /^settings$/i },
  { path: "/analytics", heading: /^analytics$/i },
];

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
