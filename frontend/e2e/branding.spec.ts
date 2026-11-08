import { test, expect, type Page } from "@playwright/test";
import { clerkAuth, isClerkConfigured } from "./helpers/auth";

/**
 * Settings › Branding — the screen that puts the agency's logo on the campaign
 * pack and the review link.
 *
 * Stubbed rather than seeded, like manual-publish.spec.ts: what is under test
 * is the screen's own behaviour — that an upload lands in the preview at once,
 * that Save sends what was typed, and above all what the copy claims. Product
 * rule 1: branding covers two client-facing surfaces and nothing else, and the
 * old "Logo upload not available yet" badge must be gone now that it is real.
 */

const ORG_ID = "00000000-0000-0000-0000-0000000000a3";

/** A 1×1 transparent PNG — enough to be a real image on both ends. */
const PIXEL = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
  "base64"
);
const PIXEL_DATA_URL = `data:image/png;base64,${PIXEL.toString("base64")}`;

function json(body: unknown) {
  return { status: 200, contentType: "application/json", body: JSON.stringify(body) };
}

interface Branding {
  id: string;
  custom_domain: null;
  logo_url: null;
  primary_color: string | null;
  company_name: string | null;
  support_email: string | null;
  portal_enabled: boolean;
  email_from_name: null;
  is_active: boolean;
  has_logo: boolean;
  logo_mime: string | null;
  logo_bytes: number | null;
  logo_data_url: string | null;
}

async function stubBranding(page: Page) {
  const state = {
    row: null as Branding | null,
    puts: [] as Record<string, unknown>[],
    uploads: 0,
  };
  const row = (): Branding =>
    state.row ?? {
      id: "00000000-0000-0000-0000-0000000000f1",
      custom_domain: null,
      logo_url: null,
      primary_color: null,
      company_name: null,
      support_email: null,
      portal_enabled: false,
      email_from_name: null,
      is_active: true,
      has_logo: false,
      logo_mime: null,
      logo_bytes: null,
      logo_data_url: null,
    };

  await page.route("**/api/v1/auth/me", (route) =>
    route.fulfill(
      json({
        user_id: "00000000-0000-0000-0000-0000000000d3",
        email: "e2e@example.com",
        role: "owner",
        org_id: ORG_ID,
        account_type: "business",
        capabilities: [
          "read",
          "campaign.run",
          "content.approve",
          "publish.write",
          "publish.manual",
          "content.override",
          "oauth.connect",
          "team.manage",
          "billing.manage",
          "workspace.manage",
        ],
      })
    )
  );
  await page.route("**/api/v1/clients/overview", (route) => route.fulfill(json({ items: [] })));
  await page.route("**/api/v1/integrations/settings", (route) =>
    route.fulfill(json({ name: "Northwind Social", domain: null, settings: {} }))
  );

  await page.route("**/api/v1/integrations/white-label/logo", (route) => {
    if (route.request().method() === "POST") {
      state.uploads += 1;
      state.row = {
        ...row(),
        has_logo: true,
        logo_mime: "image/png",
        logo_bytes: PIXEL.length,
        logo_data_url: PIXEL_DATA_URL,
      };
      return route.fulfill(json(state.row));
    }
    if (route.request().method() === "DELETE") {
      state.row = { ...row(), has_logo: false, logo_mime: null, logo_bytes: null, logo_data_url: null };
      return route.fulfill(json(state.row));
    }
    return route.continue();
  });

  await page.route("**/api/v1/integrations/white-label", (route) => {
    if (route.request().method() === "PUT") {
      const body = (route.request().postDataJSON() ?? {}) as Record<string, unknown>;
      state.puts.push(body);
      state.row = {
        ...row(),
        company_name: (body.company_name as string) || null,
        primary_color: (body.primary_color as string) || null,
        support_email: (body.support_email as string) || null,
        is_active: body.is_active !== false,
      };
      return route.fulfill(json(state.row));
    }
    return route.fulfill(json(state.row ?? { is_active: false }));
  });

  return state;
}

test.describe("Settings › Branding", () => {
  test.beforeEach(async ({ page }) => {
    test.skip(!isClerkConfigured(), "Clerk keys not configured");
    await clerkAuth(page);
  });

  test("uploads a logo into the preview and saves the name", async ({ page }) => {
    const state = await stubBranding(page);
    await page.goto("/settings?tab=branding", { waitUntil: "domcontentloaded" });

    await expect(page.getByRole("heading", { name: "Agency branding" })).toBeVisible();
    // Scope, stated on the screen: two client-facing surfaces, no custom domain.
    await expect(page.getByText("there is no custom domain")).toBeVisible();
    await expect(page.getByText("No logo yet")).toBeVisible();

    await page.locator("#branding-logo-file").setInputFiles({
      name: "logo.png",
      mimeType: "image/png",
      buffer: PIXEL,
    });
    await expect(page.getByText("Logo uploaded")).toBeVisible();
    expect(state.uploads).toBe(1);
    await expect(page.getByTestId("branding-logo-preview").locator("img")).toHaveAttribute(
      "src",
      PIXEL_DATA_URL
    );
    // The cover mock-up shows the same logo the pack will carry.
    await expect(page.getByTestId("branding-preview").locator("img")).toHaveAttribute(
      "src",
      PIXEL_DATA_URL
    );
    await expect(page.getByRole("button", { name: "Replace logo" })).toBeVisible();

    await page.locator("#branding-company-name").fill("Northwind Social Studio");
    await expect(page.getByTestId("branding-preview")).toContainText("Prepared by Northwind Social Studio");
    await page.getByRole("button", { name: "Save branding" }).click();
    await expect(page.getByText("Branding saved")).toBeVisible();
    expect(state.puts).toHaveLength(1);
    expect(state.puts[0]).toMatchObject({ company_name: "Northwind Social Studio", is_active: true });
  });

  test("switched off, the preview falls back to the workspace name", async ({ page }) => {
    await stubBranding(page);
    await page.goto("/settings?tab=branding", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: "Agency branding" })).toBeVisible();

    await page.locator("#branding-company-name").fill("Someone Else");
    await page.locator("#branding-is-active").uncheck();
    await expect(page.getByTestId("branding-preview")).toContainText("Prepared by Northwind Social");
    await expect(page.getByTestId("branding-preview")).not.toContainText("Someone Else");
  });

  test("the Workspace tab no longer claims the logo is unavailable", async ({ page }) => {
    await stubBranding(page);
    await page.goto("/settings?tab=general", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: "Organization" })).toBeVisible();
    await expect(page.getByText("Logo upload not available yet")).toHaveCount(0);
    await page.getByRole("button", { name: "Branding", exact: true }).first().click();
    await expect(page.getByRole("heading", { name: "Agency branding" })).toBeVisible();
  });
});
