import { clerkSetup } from "@clerk/testing/playwright";
import { config } from "dotenv";
import { resolve } from "path";

export default async function globalSetup() {
  config({ path: resolve(__dirname, "../.env.local") });

  const sk = process.env.CLERK_SECRET_KEY ?? "";
  if (!sk || sk === "sk_test_xxxxx") {
    console.warn("[clerk] No valid CLERK_SECRET_KEY — Clerk auth tests will be skipped.");
    return;
  }
  await clerkSetup();
}
