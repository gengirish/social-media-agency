import { test, expect, type Page } from "@playwright/test";

/**
 * The page an agency's client opens from a review link (`/review/[token]`).
 *
 * Public — no Clerk session — so nothing here signs in. The API is stubbed: a real
 * link needs a client, a pending post and a member seat to create it, and the
 * server side (scope, expiry, moderation, notifications) is covered by
 * backend/tests/test_client_review.py and test_tenancy_routers.py. What is under
 * test is the page's own behaviour: what it shows, which body it sends, and how it
 * explains an ended link or a held approval.
 */

const TOKEN = "rv_e2e-token";
const POST_ID = "00000000-0000-0000-0000-0000000000d1";
const BODY = "Cold brew is back. Same beans, slower pour.";

function page(overrides: Record<string, unknown> = {}) {
  return {
    agency: { name: "Northwind Social", logo_url: null, primary_color: null, support_email: null },
    client: { name: "Sunrise Coffee" },
    campaign: { id: "c1", name: "Cold Brew Launch" },
    expires_at: new Date(Date.now() + 10 * 86_400_000).toISOString(),
    pending: [
      {
        id: POST_ID,
        platform: "linkedin",
        content_type: "social_post",
        title: "",
        body: BODY,
        hashtags: ["coldbrew"],
        media_urls: [],
        status: "pending",
        scheduled_at: null,
        client_review: null,
      },
    ],
    decided: [],
    ...overrides,
  };
}

function json(body: unknown, status = 200) {
  return { status, contentType: "application/json", body: JSON.stringify(body) };
}

async function stubReview(p: Page, decide: (body: Record<string, unknown>) => { status: number; body: unknown }) {
  const sent: Record<string, unknown>[] = [];
  await p.route(`**/api/v1/portal/review/${TOKEN}`, (route) => route.fulfill(json(page())));
  await p.route(`**/api/v1/portal/review/${TOKEN}/content/${POST_ID}`, (route) => {
    const body = route.request().postDataJSON() as Record<string, unknown>;
    sent.push(body);
    const res = decide(body);
    return route.fulfill(json(res.body, res.status));
  });
  return sent;
}

test.describe("Client review page", () => {
  test("shows the agency, not CampaignForge, and approves a post", async ({ page: p }) => {
    const sent = await stubReview(p, () => ({
      status: 200,
      body: { item: { ...page().pending[0], status: "approved", client_review: { decision: "approved" } } },
    }));
    await p.goto(`/review/${TOKEN}`);

    await expect(p.getByRole("heading", { level: 1, name: "Cold Brew Launch" })).toBeVisible();
    await expect(p.getByText("Northwind Social", { exact: true })).toBeVisible();
    await expect(p.getByText("CampaignForge")).toHaveCount(0);
    await expect(p.getByText(BODY)).toBeVisible();

    await p.getByLabel(/Your name/).fill("Dana");
    await p.getByRole("button", { name: "Approve" }).click();

    await expect(p.getByText("Approved", { exact: true })).toBeVisible();
    await expect(p.getByRole("button", { name: "Approve" })).toHaveCount(0);
    expect(sent).toEqual([{ decision: "approve", name: "Dana" }]);
  });

  test("request changes needs a comment and sends it", async ({ page: p }) => {
    const sent = await stubReview(p, (body) => ({
      status: 200,
      body: {
        item: {
          ...page().pending[0],
          client_review: { decision: "changes_requested", comment: body.comment, name: null },
        },
      },
    }));
    await p.goto(`/review/${TOKEN}`);

    await p.getByRole("button", { name: "Request changes" }).click();
    const send = p.getByRole("button", { name: "Send to agency" });
    await expect(send).toBeDisabled();
    await p.getByLabel("What should change?").fill("Mention the oat milk option");
    await send.click();

    await expect(p.getByText("Changes requested")).toBeVisible();
    await expect(p.getByText("Mention the oat milk option")).toBeVisible();
    expect(sent).toEqual([{ decision: "request_changes", comment: "Mention the oat milk option" }]);
  });

  test("a held approval says the agency will check it, and offers nothing else", async ({ page: p }) => {
    await stubReview(p, () => ({
      status: 409,
      body: { detail: { code: "approval_held", message: "held" } },
    }));
    await p.goto(`/review/${TOKEN}`);
    await p.getByRole("button", { name: "Approve" }).click();

    await expect(p.getByText(/your agency needs to check this post/i)).toBeVisible();
    await expect(p.getByRole("button", { name: "Approve" })).toHaveCount(0);
    await expect(p.getByRole("button", { name: "Request changes" })).toHaveCount(0);
    // The moderation reason is the agency's, never the client's.
    await expect(p.getByText(/moderation/i)).toHaveCount(0);
  });

  test("an expired link says it has ended", async ({ page: p }) => {
    await p.route(`**/api/v1/portal/review/${TOKEN}`, (route) =>
      route.fulfill(
        json(
          {
            detail: {
              code: "link_expired",
              message: "This review link has expired. Ask your agency for a new one.",
            },
          },
          410
        )
      )
    );
    await p.goto(`/review/${TOKEN}`);
    await expect(p.getByRole("heading", { name: "This link has ended" })).toBeVisible();
    await expect(p.getByText("Ask your agency for a new one")).toBeVisible();
    await expect(p.getByRole("button", { name: "Try again" })).toHaveCount(0);
  });
});
