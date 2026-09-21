/*
 * Dashboard information architecture — Cadence's grouped nav, mapped onto the
 * existing routes (docs/cadence-port-plan-260921.md §3). Routes did not move;
 * only the grouping is new. Pure data + a pure resolver, no React.
 */

export type NavIconName = "setup" | "posts" | "create" | "insights" | "settings";

export interface NavTab {
  label: string;
  href: string;
  /** Path prefix this tab owns. Defaults to href's path. */
  path?: string;
  /** Required `?tab=` value, for pages that expose sub-sections via the query string. */
  queryTab?: string;
}

export interface NavGroup {
  id: NavIconName;
  label: string;
  tabs: NavTab[];
}

export const NAV_GROUPS: NavGroup[] = [
  {
    id: "setup",
    label: "Setup",
    tabs: [
      { label: "Clients", href: "/clients" },
      { label: "Accounts", href: "/settings?tab=platforms", path: "/settings", queryTab: "platforms" },
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
    id: "create",
    label: "Create",
    tabs: [
      { label: "Campaigns", href: "/campaigns" },
      { label: "Templates", href: "/templates" },
    ],
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
      { label: "Team", href: "/team" },
      { label: "Billing", href: "/pricing" },
    ],
  },
];

function tabPath(tab: NavTab): string {
  return tab.path ?? tab.href.split("?")[0];
}

/**
 * The active group and tab for a location. A tab that also matches the query
 * (`/settings?tab=platforms` → Setup › Accounts) beats a path-only match
 * (`/settings` → Settings › Workspace); a longer path beats a shorter one.
 */
export function resolveNav(pathname: string, queryTab: string | null): { group: NavGroup; tab: NavTab } | null {
  let best: { group: NavGroup; tab: NavTab; score: number } | null = null;
  for (const group of NAV_GROUPS) {
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
