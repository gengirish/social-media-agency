"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect } from "react";
import { setClerkTokenGetter } from "@/lib/api";

/**
 * Wires Clerk's `getToken` into the API client, and — just as importantly —
 * tells it when Clerk has actually hydrated.
 *
 * `isLoaded` is the whole point of the second argument. Until Clerk finishes
 * loading, `getToken()` resolves `null`, and a request sent in that window
 * carries no Authorization header and comes back 401. Dashboard screens fetch
 * from a mount effect, so for a user whose session was created in the same
 * navigation (i.e. everyone signing up) that window is exactly when the first
 * page load happens. `lib/api.ts` holds authenticated requests until this flips.
 */
export function ClerkTokenSync() {
  const { getToken, isLoaded } = useAuth();

  useEffect(() => {
    setClerkTokenGetter(getToken, isLoaded);
  }, [getToken, isLoaded]);

  return null;
}
