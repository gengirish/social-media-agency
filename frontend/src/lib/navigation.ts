/*
 * Dashboard information architecture — Cadence's grouped nav, mapped onto the
 * existing routes (docs/cadence-port-plan-260921.md §3). Routes did not move;
 * only the grouping is new. Pure data + a pure resolver, no React.
 */

import type { Capability } from "@/lib/session";

export type NavIconName = "setup" | "posts" | "create" | "ads" | "inbox" | "insights" | "settings";

export interface NavTab {
  label: string;
  href: string;
  /** Path prefix this tab owns. Defaults to href's path. */
  path?: string;
  /** Required `?tab=` value, for pages that expose sub-sections via the query string. */
  queryTab?: string;
  /**
   * Capability the viewer needs before this tab is shown. Presentation only —
   * the route itself is gated server-side (`require_cap`, 403
   * `insufficient_permissions`); hiding the tab just avoids offering a button
   * that will reject the person. Filtering happens in the nav components, not
   * here: this module stays pure data.
   */
  requires?: Capability;
}

export interface NavGroup {
  id: NavIconName;
  label: string;
  tabs: NavTab[];
}

/*
 * Group order is also the keyboard-shortcut order (1–7). Cadence's order is
 * Setup, Posts, Create; this app deliberately puts Create before Posts
 * (commit 70a67a9) because a Queue is empty until something has been created.
 */
export const NAV_GROUPS: NavGroup[] = [
  {
    id: "setup",
    label: "Setup",
    tabs: [
      { label: "Profile", href: "/setup/profile" },
      { label: "Clients", href: "/clients" },
      { label: "Accounts", href: "/setup/accounts" },
    ],
  },
  {
    id: "create",
    label: "Create",
    tabs: [
      { label: "Campaigns", href: "/campaigns" },
      { label: "Content", href: "/create/content" },
      { label: "Email", href: "/create/email" },
      { label: "Launch", href: "/create/launch" },
      { label: "Amplify", href: "/amplify" },
    ],
  },
  /*
   * Ads is its own group rather than a Create tab: paid copy has a separate
   * review path (services/ad_guardrails.py) and never becomes a content_piece,
   * so it does not share Create's approval-queue destination. Templates moved
   * in with it at the user's request -- see the note in templates/page.tsx.
   */
  {
    id: "ads",
    label: "Ads",
    tabs: [
      { label: "Ads", href: "/create/ads" },
      { label: "Templates", href: "/templates" },
    ],
  },
  {
    id: "posts",
    label: "Posts",
    tabs: [
      { label: "Queue", href: "/content" },
      { label: "Calendar", href: "/calendar" },
    ],
  },
  {
    id: "inbox",
    label: "Inbox",
    tabs: [{ label: "Inbox", href: "/inbox" }],
  },
  {
    id: "insights",
    label: "Insights",
    tabs: [{ label: "Analytics", href: "/analytics" }],
  },
  {
    id: "settings",
    label: "Settings",
    tabs: [
      { label: "Workspace", href: "/settings" },
      { label: "Team", href: "/team", requires: "team.manage" },
      { label: "Billing", href: "/pricing", requires: "billing.manage" },
    ],
  },
];

/** Routes outside the groups that still get a breadcrumb title. */
export const STANDALONE_TITLES: Record<string, string> = {
  "/welcome": "Welcome",
  "/legal": "Legal",
};

function tabPath(tab: NavTab): string {
  return tab.path ?? tab.href.split("?")[0];
}

/**
 * The active group and tab for a location. A tab that also matches the query
 * (`/settings?tab=platforms` → Setup › Accounts) beats a path-only match
 * (`/settings` → Settings › Workspace); a longer path beats a shorter one.
 *
 * Pure: `groups` defaults to the full set, and a caller that hides tabs by
 * capability passes its already-filtered groups in. Capability lookups never
 * happen inside here.
 */
export function resolveNav(
  pathname: string,
  queryTab: string | null,
  groups: NavGroup[] = NAV_GROUPS
): { group: NavGroup; tab: NavTab } | null {
  let best: { group: NavGroup; tab: NavTab; score: number } | null = null;
  for (const group of groups) {
    for (const tab of group.tabs) {
      const path = tabPath(tab);
      if (pathname !== path && !pathname.startsWith(path + "/")) continue;
      if (tab.queryTab && tab.queryTab !== queryTab) continue;
      const score = path.length + (tab.queryTab ? 1000 : 0);
      if (!best || score > best.score) best = { group, tab, score };
    }
  }
  return best && { group: best.group, tab: best.tab };
}
