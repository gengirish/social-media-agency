"use client";

import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";
import { Toaster } from "sonner";
import { applyTheme, currentTheme, type Theme } from "@/lib/theme";

/** The live theme, tracking the `dark` class on <html> wherever it gets set. */
export function useTheme(): Theme {
  const [theme, setTheme] = useState<Theme>("light");
  useEffect(() => {
    setTheme(currentTheme());
    const observer = new MutationObserver(() => setTheme(currentTheme()));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);
  return theme;
}

/*
 * The server cannot know the theme, so the icon is chosen by CSS (`dark:`)
 * rather than state — no stale icon between first paint and hydration — and
 * the click reads the live class instead of a possibly-stale render value.
 */
export function ThemeToggle() {
  return (
    <button
      type="button"
      onClick={() => applyTheme(currentTheme() === "dark" ? "light" : "dark")}
      aria-label="Toggle light and dark theme"
      title="Toggle light and dark theme"
      className="press-scale flex h-8 w-8 items-center justify-center rounded-md border border-line text-muted transition-colors hover:border-accent/40 hover:text-ink"
    >
      <Moon className="h-4 w-4 dark:hidden" />
      <Sun className="hidden h-4 w-4 dark:block" />
    </button>
  );
}

export function ThemedToaster() {
  const theme = useTheme();
  return <Toaster position="top-right" richColors theme={theme} />;
}
