"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import { useAuth } from "@clerk/nextjs";
import { initAnalytics, trackPageView } from "@/lib/analytics";

/**
 * Mounts the product-analytics session and reports a page view on every route
 * change. Signed-out visitors are not tracked — the ingest endpoint requires a
 * token, so events would be dropped anyway.
 */
export function AnalyticsTracker() {
  const pathname = usePathname();
  const { isSignedIn } = useAuth();

  useEffect(() => {
    if (!isSignedIn) return;
    return initAnalytics();
  }, [isSignedIn]);

  useEffect(() => {
    if (!isSignedIn || !pathname) return;
    trackPageView(pathname);
  }, [isSignedIn, pathname]);

  return null;
}
