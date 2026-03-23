import { test, expect } from "@playwright/test";

const API_URL = process.env.API_URL || "https://campaignforge-api.fly.dev";

test.describe("API Health", () => {
  test("backend health check returns ok", async ({ request }) => {
    const response = await request.get(`${API_URL}/api/v1/health`);
    expect(response.ok()).toBeTruthy();
    const body = await response.json();
    expect(body.status).toBe("healthy");
  });

  test("API docs are accessible", async ({ request }) => {
    const response = await request.get(`${API_URL}/api/docs`);
    expect(response.ok()).toBeTruthy();
  });
});
