"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { UserPlus } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { EmptyState, LoadingState } from "@/components/ui/empty-state";
import { ErrorBanner } from "@/components/ui/feedback";
import { useActiveClient } from "@/lib/active-client";

/**
 * Loading / error / no-client states for the Setup screens, which all act on
 * the active client (Cadence's active product). Renders children once a client
 * is active.
 */
export function ActiveClientGate({ children }: { children: ReactNode }) {
  const { active, loading, error, refresh } = useActiveClient();
  if (loading) return <LoadingState label="Loading your clients…" />;
  if (error) return <ErrorBanner message="Couldn't load your clients." onRetry={() => void refresh()} />;
  if (!active) {
    return (
      <EmptyState
        icon={UserPlus}
        title="Add a client first"
        description="Setup works on one client at a time — the one picked in the switcher at the top."
        action={
          <Link href="/clients?new=1" className={buttonVariants()}>
            <UserPlus className="h-3.5 w-3.5" /> Add a client
          </Link>
        }
      />
    );
  }
  return <>{children}</>;
}
