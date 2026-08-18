"use client";

import Link from "next/link";
import { useAuth } from "@clerk/nextjs";

/**
 * Auth-aware call-to-action for the landing page.
 *
 * The landing page is a Server Component so the design ships as static HTML.
 * Only these buttons depend on session state, so they are the one client
 * island rather than making the whole page "use client".
 */
export function AuthCta({ variant }: { variant: "header" | "hero" | "final" }) {
  const { isLoaded, isSignedIn } = useAuth();

  if (variant === "header") {
    if (!isLoaded) {
      // Reserve the button's footprint so the header does not reflow on load.
      return <span className="cf-auth-skeleton" aria-hidden />;
    }
    if (isSignedIn) {
      return (
        <Link href="/campaigns" className="cf-btn cf-btn-solid cf-btn-sm">
          Go to dashboard
        </Link>
      );
    }
    return (
      <>
        <Link href="/sign-in" className="cf-navlink">
          Sign in
        </Link>
        <Link href="/sign-up" className="cf-btn cf-btn-solid cf-btn-sm">
          Start free
        </Link>
      </>
    );
  }

  const signedInHref = "/campaigns";
  const signedInLabel = "Go to dashboard";

  if (variant === "hero") {
    return (
      <Link
        href={isLoaded && isSignedIn ? signedInHref : "/sign-up"}
        className="cf-btn cf-btn-accent"
      >
        {isLoaded && isSignedIn ? signedInLabel : "Start free"}
      </Link>
    );
  }

  return (
    <Link
      href={isLoaded && isSignedIn ? signedInHref : "/sign-up"}
      className="cf-btn cf-btn-solid cf-btn-lg"
    >
      {isLoaded && isSignedIn ? signedInLabel : "Start free"}
    </Link>
  );
}
