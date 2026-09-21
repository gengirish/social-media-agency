"use client";

import Link from "next/link";
import { useEffect, useState, type ComponentType } from "react";
import { UserButton } from "@clerk/nextjs";
import { ListChecks, Menu, Settings, Sparkles, TrendingUp, Wand2, X } from "lucide-react";
import { NotificationsBell } from "@/components/notifications-bell";
import { ThemeToggle } from "@/components/theme";
import { NAV_GROUPS, resolveNav, type NavIconName } from "@/lib/navigation";
import { cn } from "@/lib/utils";

const ICONS: Record<NavIconName, ComponentType<{ className?: string }>> = {
  setup: Sparkles,
  posts: ListChecks,
  create: Wand2,
  insights: TrendingUp,
  settings: Settings,
};

/**
 * Cadence top bar: brand + breadcrumb, grouped pills, sub-tabs for the active
 * group. Presentational — the caller supplies the location, so the layout can
 * render it both inside and outside a Suspense boundary for useSearchParams.
 */
export function AppNav({ pathname, queryTab }: { pathname: string; queryTab: string | null }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const active = resolveNav(pathname, queryTab);

  useEffect(() => setMenuOpen(false), [pathname, queryTab]);

  return (
    <header className="sticky top-0 z-40 border-b border-line bg-canvas/75 shadow-[0_1px_0_rgb(var(--c-accent)/0.08)] backdrop-blur-xl">
      <div className="flex h-16 items-center gap-4 px-4 sm:px-6">
        <Link href="/campaigns" className="flex min-w-0 items-center gap-2.5" aria-label="CampaignForge home">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-accent bg-accent/10 text-accent-text">
            <Sparkles className="h-3.5 w-3.5 motion-safe:animate-logo-spin" />
          </span>
          <span className="truncate font-mono text-sm tracking-[0.15em] text-ink">
            CAMPAIGNFORGE
            {active && (
              <>
                <span className="text-accent-text">/</span>
                <span className="text-muted">{active.tab.label.toUpperCase()}</span>
              </>
            )}
          </span>
        </Link>

        <nav aria-label="Primary" className="ml-auto hidden items-center gap-1 lg:flex">
          {NAV_GROUPS.map((group) => {
            const Icon = ICONS[group.id];
            const isActive = active?.group.id === group.id;
            return (
              <Link
                key={group.id}
                href={group.tabs[0].href}
                aria-current={isActive ? "page" : undefined}
                className={cn(
                  "flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-[13px] font-medium transition-all duration-200",
                  isActive
                    ? "border-accent bg-accent text-on-accent shadow-glow"
                    : "border-transparent text-muted hover:-translate-y-px hover:border-accent/30 hover:bg-accent/10 hover:text-ink"
                )}
              >
                <Icon className="h-3.5 w-3.5" />
                {group.label}
              </Link>
            );
          })}
        </nav>

        <div className="ml-auto flex items-center gap-2 lg:ml-2">
          <ThemeToggle />
          <NotificationsBell />
          <UserButton />
          <button
            type="button"
            onClick={() => setMenuOpen((o) => !o)}
            aria-expanded={menuOpen}
            aria-controls="mobile-nav"
            className="flex items-center gap-1.5 rounded-md border border-line px-2.5 py-1.5 text-[13px] font-medium text-muted lg:hidden"
          >
            {menuOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
            Menu
          </button>
        </div>
      </div>

      {menuOpen && (
        <nav id="mobile-nav" aria-label="Primary" className="border-t border-line px-4 py-3 lg:hidden">
          {NAV_GROUPS.map((group) => {
            const Icon = ICONS[group.id];
            return (
              <div key={group.id} className="py-1.5">
                <div className="mb-1 flex items-center gap-1.5 text-xs font-medium text-muted">
                  <Icon className="h-3.5 w-3.5" />
                  {group.label}
                </div>
                <div className="flex flex-wrap gap-1.5 pl-5">
                  {group.tabs.map((tab) => (
                    <SubTabLink key={tab.href} href={tab.href} label={tab.label} active={active?.tab === tab} />
                  ))}
                </div>
              </div>
            );
          })}
        </nav>
      )}

      {active && active.group.tabs.length > 1 && (
        <nav aria-label={`${active.group.label} sections`} className="hidden gap-2 px-4 pb-3 sm:px-6 lg:flex">
          {active.group.tabs.map((tab) => (
            <SubTabLink key={tab.href} href={tab.href} label={tab.label} active={active.tab === tab} />
          ))}
        </nav>
      )}
    </header>
  );
}

function SubTabLink({ href, label, active }: { href: string; label: string; active: boolean }) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "rounded-md border px-3 py-1 text-[12.5px] font-medium transition-colors",
        active ? "border-accent bg-accent text-on-accent" : "border-line text-muted hover:border-slate-300 hover:text-ink"
      )}
    >
      {label}
    </Link>
  );
}
