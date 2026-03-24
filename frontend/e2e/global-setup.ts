import { clerkSetup } from "@clerk/testing/playwright";
import { config } from "dotenv";
import { resolve } from "path";
import { test as setup } from "@playwright/test";

config({ path: resolve(__dirname, "../.env.local") });

setup.describe.configure({ mode: "serial" });

setup("clerk global setup", async ({}) => {
  const sk = process.env.CLERK_SECRET_KEY ?? "";
  if (!sk || sk === "sk_test_xxxxx") {
    console.warn("[clerk] No valid CLERK_SECRET_KEY — Clerk auth tests will be skipped.");
    return;
  }
  await clerkSetup();
});
