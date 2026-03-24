import { clerkSetup } from "@clerk/testing/playwright";

export default async function globalSetup() {
  const sk = process.env.CLERK_SECRET_KEY ?? "";
  if (!sk || sk.startsWith("sk_test_xxxxx")) {
    console.warn("[clerk] No valid CLERK_SECRET_KEY — Clerk auth tests will be skipped.");
    return;
  }
  await clerkSetup();
}
