"use client";

/*
 * The signed-in viewer's role and capabilities — the frontend half of the RBAC
 * work (docs/rbac-phase-plan-260923.md).
 *
 * Sourced from `GET /api/v1/auth/me`, which resolves the role from the database
 * rather than the JWT's `role` claim, so a demotion takes effect on the next
 * load instead of at token expiry.
 *
 * This is presentation only. Hiding a control here protects nothing — every
 * capability is enforced server-side by `require_cap` in the routers, and the
 * API returns 403 `insufficient_permissions` regardless of what the UI renders.
 * The point is that a person should not be shown a button that will reject them.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { ApiError, request } from "@/lib/api";

/** Mirrors `Capability` in backend/src/agency/permissions.py. */
export type Capability =
  | "read"
  | "campaign.run"
  | "content.approve"
  | "publish.write"
  | "content.override"
  | "oauth.connect"
  | "team.manage"
  | "billing.manage";

export type Role = "owner" | "admin" | "member" | "viewer";
export type AccountType = "personal" | "business";

export interface Me {
  user_id: string;
  email: string;
  role: Role;
  org_id: string;
  account_type: AccountType;
  capabilities: Capability[];
}

interface SessionValue {
  me: Me | null;
  loading: boolean;
  /** True when `/auth/me` 404s — the session is invalid, not merely read-only. */
  invalid: boolean;
  /** Capability check. False while loading, so nothing flashes before it is known. */
  can: (cap: Capability) => boolean;
  isPersonal: boolean;
  refresh: () => Promise<void>;
}

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [invalid, setInvalid] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setMe(await request<Me>("/api/v1/auth/me"));
      setInvalid(false);
    } catch (err) {
      // 404 means no active user row matches this token — a broken session, not
      // a read-only one. Anything else (offline, 5xx) leaves `me` null and every
      // `can()` false, which fails closed the same way the server does.
      setInvalid(err instanceof ApiError && err.status === 404);
      setMe(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const value = useMemo<SessionValue>(() => {
    const caps = new Set(me?.capabilities ?? []);
    return {
      me,
      loading,
      invalid,
      can: (cap: Capability) => caps.has(cap),
      isPersonal: me?.account_type === "personal",
      refresh,
    };
  }, [me, loading, invalid, refresh]);

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

/**
 * The viewer's session. Returns a fail-closed stub outside the provider so a
 * component rendered in isolation (a test, a storybook) hides privileged
 * controls rather than throwing.
 */
export function useSession(): SessionValue {
  return (
    useContext(SessionContext) ?? {
      me: null,
      loading: true,
      invalid: false,
      can: () => false,
      isPersonal: false,
      refresh: async () => {},
    }
  );
}
