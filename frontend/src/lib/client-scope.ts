"use client";

import { useCallback, useEffect, useState } from "react";

/**
 * "This client" vs "All clients", shared across the screens that offer the
 * choice (CF-10).
 *
 * The Queue and the Calendar each kept their own `useState`, so switching from
 * Queue (All clients) to Calendar silently reset the view to the active client
 * and the user saw a different set of posts than the one they had just been
 * looking at. One store, so the choice survives the move.
 *
 * It lives in `localStorage` and is a convenience, not data: it is per-browser,
 * never read back by the server, and every consumer works if it comes back
 * empty. Reads and writes are wrapped because a private window, blocked site
 * data or a prerender pass can make either throw.
 */
export type ClientScope = "client" | "all";

const KEY = "cf-client-scope";

function read(): ClientScope {
  try {
    return window.localStorage.getItem(KEY) === "all" ? "all" : "client";
  } catch {
    return "client";
  }
}

/**
 * The shared scope and a setter.
 *
 * Starts at "client" on the server and on the first client render, then adopts
 * the stored value in an effect — reading `localStorage` during render would
 * make the markup differ from the server's and trip hydration.
 */
export function useClientScope(): [ClientScope, (next: ClientScope) => void] {
  const [scope, setScopeState] = useState<ClientScope>("client");

  useEffect(() => {
    const stored = read();
    if (stored !== "client") setScopeState(stored);
  }, []);

  const setScope = useCallback((next: ClientScope) => {
    setScopeState(next);
    try {
      window.localStorage.setItem(KEY, next);
    } catch {
      // Not worth telling anyone about: the choice still applies to this page,
      // it just will not be remembered on the next one.
    }
  }, []);

  return [scope, setScope];
}
