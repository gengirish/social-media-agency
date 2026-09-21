/*
 * Light/dark theme. The choice is a per-viewer convenience, so localStorage is
 * the right home for it; with nothing stored, the OS preference wins.
 */

export type Theme = "light" | "dark";

export const THEME_STORAGE_KEY = "cf-theme";

/**
 * Runs inline in <head> before first paint, so a dark-mode viewer never sees a
 * light flash. Kept as a string because it must execute before React hydrates.
 */
export const THEME_INIT_SCRIPT = `(function(){try{var t=localStorage.getItem("${THEME_STORAGE_KEY}");var d=t?t==="dark":window.matchMedia("(prefers-color-scheme: dark)").matches;document.documentElement.classList.toggle("dark",d)}catch(e){}})();`;

export function currentTheme(): Theme {
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

export function applyTheme(theme: Theme): void {
  document.documentElement.classList.toggle("dark", theme === "dark");
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // Private mode or blocked storage: the toggle still works for this page view.
  }
}
