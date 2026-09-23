"use client";

/*
 * The active client — CampaignForge's equivalent of Cadence's product switcher.
 * Every Create / Posts / Insights screen scopes to it, as Cadence scopes every
 * screen to the active product. The chosen id persists in localStorage as a
 * per-viewer convenience only: it is re-validated against the org's real client
 * list on every load, so a stale or foreign id silently falls back.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { foundationApi, type ClientOverview } from "@/lib/api-foundation";

const STORAGE_KEY = "cf-active-client";

interface ActiveClientValue {
  clients: ClientOverview[];
  active: ClientOverview | null;
  activeId: string | null;
  setActiveId: (id: string) => void;
  loading: boolean;
  error: boolean;
  /** Re-read counts and setup progress — call after creating/approving/publishing. */
  refresh: () => Promise<void>;
}

const ActiveClientContext = createContext<ActiveClientValue | null>(null);

function readStored(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function writeStored(id: string) {
  try {
    window.localStorage.setItem(STORAGE_KEY, id);
  } catch {
    // Private mode / blocked storage: the switch still applies for this session.
  }
}

export function ActiveClientProvider({ children }: { children: ReactNode }) {
  const [clients, setClients] = useState<ClientOverview[]>([]);
  const [activeId, setActiveIdState] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const { items } = await foundationApi.clientsOverview();
      setClients(items);
      setError(false);
      setActiveIdState((current) => {
        const wanted = current ?? readStored();
        if (wanted && items.some((c) => c.id === wanted)) return wanted;
        return items[0]?.id ?? null;
      });
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const setActiveId = useCallback((id: string) => {
    setActiveIdState(id);
    writeStored(id);
  }, []);

  const value = useMemo<ActiveClientValue>(
    () => ({
      clients,
      active: clients.find((c) => c.id === activeId) ?? null,
      activeId,
      setActiveId,
      loading,
      error,
      refresh,
    }),
    [clients, activeId, setActiveId, loading, error, refresh]
  );

  return <ActiveClientContext.Provider value={value}>{children}</ActiveClientContext.Provider>;
}

export function useActiveClient(): ActiveClientValue {
  const ctx = useContext(ActiveClientContext);
  if (!ctx) throw new Error("useActiveClient must be used inside ActiveClientProvider");
  return ctx;
}

/** Hostname-ish label, like Cadence's product name derived from the URL. */
export function clientLabel(c: Pick<ClientOverview, "brand_name" | "website_url"> | null | undefined): string {
  if (!c) return "No client";
  return c.brand_name || c.website_url?.replace(/^https?:\/\//, "").replace(/\/$/, "") || "Untitled client";
}
