"use client";

import { Suspense, useState } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import { AnalyticsTracker } from "@/components/analytics-tracker";
import { AppNav } from "@/components/layout/app-nav";
import { AppFooter, KeyboardShortcuts, useLastVisited } from "@/components/layout/shell-extras";
import { ActiveClientProvider } from "@/lib/active-client";
import { SessionProvider } from "@/lib/session";

// useSearchParams must sit under a Suspense boundary or every dashboard page
// bails out of static rendering; the fallback renders the same bar path-only.
function ShellWithQuery({ onShortcutsOpen, shortcutsOpen }: { onShortcutsOpen: (o: boolean) => void; shortcutsOpen: boolean }) {
  const pathname = usePathname();
  const params = useSearchParams();
  const queryTab = params.get("tab");
  const lastVisited = useLastVisited(pathname, queryTab);
  return (
    <>
      <AppNav pathname={pathname} queryTab={queryTab} lastVisited={lastVisited} />
      <KeyboardShortcuts lastVisited={lastVisited} open={shortcutsOpen} onOpenChange={onShortcutsOpen} />
    </>
  );
}

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  return (
    <SessionProvider>
      <ActiveClientProvider>
        <div className="app-shell app-canvas relative min-h-screen overflow-x-hidden">
          {/* Cadence's ambient depth: two slow-drifting glows behind the interface. */}
          <div aria-hidden className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
            <div className="absolute -left-[8%] -top-[10%] h-[55vw] max-h-[720px] w-[55vw] max-w-[720px] animate-blob-1 rounded-full bg-[radial-gradient(circle,rgb(var(--c-accent)/0.14)_0%,transparent_70%)] blur-[60px]" />
            <div className="absolute -bottom-[15%] -right-[10%] h-[60vw] max-h-[780px] w-[60vw] max-w-[780px] animate-blob-2 rounded-full bg-[radial-gradient(circle,rgb(94_161_255/0.10)_0%,transparent_70%)] blur-[70px]" />
            <div className="absolute left-1/2 top-[35%] h-[40vw] max-h-[560px] w-[40vw] max-w-[560px] animate-blob-1 rounded-full bg-[radial-gradient(circle,rgb(92_214_166/0.08)_0%,transparent_70%)] blur-[80px] [animation-direction:reverse] [animation-duration:30s]" />
          </div>
          <AnalyticsTracker />
          <Suspense fallback={<AppNav pathname={pathname} queryTab={null} />}>
            <ShellWithQuery shortcutsOpen={shortcutsOpen} onShortcutsOpen={setShortcutsOpen} />
          </Suspense>
          <main key={pathname} className="relative z-[1] mx-auto max-w-7xl animate-screen-in p-4 sm:p-6 lg:p-8">
            {children}
          </main>
          <div className="relative z-[1]">
            <AppFooter onShowShortcuts={() => setShortcutsOpen(true)} />
          </div>
        </div>
      </ActiveClientProvider>
    </SessionProvider>
  );
}
