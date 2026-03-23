import { test, expect } from "@playwright/test";
import { buildTestUser, signupViaApi, loginAs } from "./helpers/auth";

type PageCheck = { path: string; heading: RegExp };

const PAGES: PageCheck[] = [
  { path: "/", heading: /^campaigns$/i },
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
  let user: ReturnType<typeof buildTestUser>;

  test.beforeAll(async ({ request }) => {
    user = buildTestUser();
    await signupViaApi(request, user);
  });

  test.beforeEach(async ({ page }) => {
    await loginAs(page, user.email, user.password);
  });

  test("dashboard routes load with primary heading", async ({ page }) => {
    for (const { path, heading } of PAGES) {
      await page.goto(path);

      if (path === "/") {
        await expect(page).toHaveURL(/\/campaigns/, { timeout: 20000 });
      } else {
        await expect(page).toHaveURL(
          new RegExp(`${path.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(/)?(\\?.*)?$`, "i"),
          { timeout: 20000 }
        );
      }

      await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible({
        timeout: 20000,
      });

      await expect(page.getByText(/application error|next\.js.*error/i)).toHaveCount(0);
    }
  });
});
