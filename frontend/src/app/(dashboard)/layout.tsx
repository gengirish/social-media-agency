"use client";

import { Suspense } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import { AnalyticsTracker } from "@/components/analytics-tracker";
import { AppNav } from "@/components/layout/app-nav";

// useSearchParams must sit under a Suspense boundary or every dashboard page
// bails out of static rendering; the fallback renders the same bar path-only.
function NavWithQuery() {
  const pathname = usePathname();
  const params = useSearchParams();
  return <AppNav pathname={pathname} queryTab={params.get("tab")} />;
}

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="app-shell app-canvas min-h-screen">
      <AnalyticsTracker />
      <Suspense fallback={<AppNav pathname={pathname} queryTab={null} />}>
        <NavWithQuery />
      </Suspense>
      <main key={pathname} className="mx-auto max-w-7xl animate-screen-in p-4 sm:p-6 lg:p-8">
        {children}
      </main>
    </div>
  );
}
