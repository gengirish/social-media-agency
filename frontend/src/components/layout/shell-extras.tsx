"use client";

/*
 * Cadence shell behaviours: remember the last sub-tab per group (so a group
 * pill returns you where you were), number-key shortcuts 1–6 + "?" help, and
 * the footer with legal links. Last-visited lives in sessionStorage — a
 * per-tab convenience, never state anything depends on.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { PostDialog } from "@/components/posts/dialog";
import { NAV_GROUPS, resolveNav, type NavGroup } from "@/lib/navigation";
import { useSession } from "@/lib/session";

const LAST_VISITED_KEY = "cf-last-visited";

/**
 * `NAV_GROUPS` with every tab the viewer lacks the capability for removed, and
 * any group left with no tabs dropped so it never renders as an empty pill.
 *
 * `can()` is false while the session is still loading, so a privileged tab
 * never flashes before capabilities are known. This is cosmetic — the routes
 * are gated server-side — but it is the single place the filtering happens, so
 * the nav, the shortcuts and last-visited all agree on what exists.
 */
export function useVisibleNavGroups(): NavGroup[] {
  const { can } = useSession();
  return useMemo(
    () =>
      NAV_GROUPS.map((group) => ({
        ...group,
        tabs: group.tabs.filter((tab) => !tab.requires || can(tab.requires)),
      })).filter((group) => group.tabs.length > 0),
    [can]
  );
}

function readLastVisited(): Record<string, string> {
  try {
    return JSON.parse(window.sessionStorage.getItem(LAST_VISITED_KEY) || "{}") as Record<string, string>;
  } catch {
    return {};
  }
}

/** Records the current location under its group; returns the group → href map. */
export function useLastVisited(pathname: string, queryTab: string | null): Record<string, string> {
  const [map, setMap] = useState<Record<string, string>>({});
  const groups = useVisibleNavGroups();
  useEffect(() => {
    const current = readLastVisited();
    const active = resolveNav(pathname, queryTab, groups);
    if (active) {
      current[active.group.id] = active.tab.href;
      try {
        window.sessionStorage.setItem(LAST_VISITED_KEY, JSON.stringify(current));
      } catch {
        // storage blocked: group pills fall back to their first tab
      }
    }
    setMap(current);
  }, [pathname, queryTab, groups]);
  return map;
}

export function groupHref(group: NavGroup, lastVisited: Record<string, string>): string {
  const remembered = lastVisited[group.id];
  return remembered && group.tabs.some((t) => t.href === remembered) ? remembered : group.tabs[0].href;
}

function isTyping(): boolean {
  const el = document.activeElement as HTMLElement | null;
  if (!el) return false;
  return el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable;
}

export function KeyboardShortcuts({
  lastVisited,
  open,
  onOpenChange,
}: {
  lastVisited: Record<string, string>;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const router = useRouter();
  const groups = useVisibleNavGroups();

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Disabled while typing or with any dialog open, as in Cadence.
      if (isTyping() || e.metaKey || e.ctrlKey || e.altKey) return;
      if (document.querySelector('[role="dialog"], [role="alertdialog"]')) return;
      const index = Number(e.key) - 1;
      if (Number.isInteger(index) && index >= 0 && index < groups.length) {
        e.preventDefault();
        router.push(groupHref(groups[index], lastVisited));
        return;
      }
      if (e.key === "?") {
        e.preventDefault();
        onOpenChange(true);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [router, lastVisited, onOpenChange, groups]);

  return (
    <PostDialog open={open} onOpenChange={onOpenChange} title="Keyboard shortcuts" className="max-w-xs">
      <div className="space-y-1.5">
        {[...groups.map((g, i) => [String(i + 1), g.label] as const), ["?", "Show this"] as const].map(([key, label]) => (
          <div key={key} className="flex items-center justify-between">
            <span className="text-xs text-slate-600">{label}</span>
            <kbd className="rounded border border-line bg-canvas px-[7px] py-px font-mono text-[11px] text-ink">{key}</kbd>
          </div>
        ))}
      </div>
      <p className="mt-3 font-mono text-[10px] text-muted">Disabled while typing or with a dialog open.</p>
    </PostDialog>
  );
}

export function AppFooter({ onShowShortcuts }: { onShowShortcuts?: () => void }) {
  return (
    <footer className="mx-auto flex max-w-6xl flex-wrap items-center justify-center gap-x-4 gap-y-1 px-6 py-6 font-mono text-[10.5px] text-muted">
      <Link href="/legal?tab=privacy" className="hover:text-ink">Privacy</Link>
      <span aria-hidden>·</span>
      <Link href="/legal?tab=terms" className="hover:text-ink">Terms</Link>
      <span aria-hidden>·</span>
      <Link href="/legal?tab=ai" className="hover:text-ink">AI-generated content notice</Link>
      {onShowShortcuts && (
        <>
          <span aria-hidden>·</span>
          <button type="button" onClick={onShowShortcuts} className="hover:text-ink">
            Keyboard shortcuts (?)
          </button>
        </>
      )}
    </footer>
  );
}
