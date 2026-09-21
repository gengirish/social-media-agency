"use client";

import Link from "next/link";
import { SignIn, SignUp } from "@clerk/nextjs";
import { Sparkles } from "lucide-react";
import { ThemeToggle, useTheme } from "@/components/theme";

/*
 * Clerk's widget renders in its own styles, so the root layout's appearance
 * (amber primary only) leaves a white card on the dark canvas. Clerk resolves
 * colors in JS, so CSS variables are not reliable here — the palette is passed
 * as literal hex per theme. Both the current (colorForeground, colorInput…)
 * and the older (colorText, colorInputBackground…) variable names are set, so
 * this holds on either side of Clerk's rename.
 */
const PALETTE = {
  light: {
    colorBackground: "#FFFFFF",
    colorForeground: "#0E1B2A",
    colorText: "#0E1B2A",
    colorMutedForeground: "#475A6D",
    colorTextSecondary: "#475A6D",
    colorInput: "#F4F6F9",
    colorInputBackground: "#F4F6F9",
    colorInputForeground: "#0E1B2A",
    colorInputText: "#0E1B2A",
    colorNeutral: "#0E1B2A",
    colorBorder: "#DDE4EC",
  },
  dark: {
    colorBackground: "#122030",
    colorForeground: "#EEF3F9",
    colorText: "#EEF3F9",
    colorMutedForeground: "#93A9BF",
    colorTextSecondary: "#93A9BF",
    colorInput: "#0E1B2A",
    colorInputBackground: "#0E1B2A",
    colorInputForeground: "#EEF3F9",
    colorInputText: "#EEF3F9",
    colorNeutral: "#EEF3F9",
    colorBorder: "#2E465E",
  },
} as const;

export function AuthCanvas({ mode }: { mode: "sign-in" | "sign-up" }) {
  const theme = useTheme();
  const appearance = {
    variables: {
      ...PALETTE[theme],
      colorPrimary: "#F2C14E",
      colorPrimaryForeground: "#1A1406",
      colorTextOnPrimaryBackground: "#1A1406",
      colorRing: "#F2C14E",
      fontFamily: "var(--font-sans), Inter, system-ui, sans-serif",
      borderRadius: "0.6rem",
    },
    elements: {
      cardBox: "shadow-soft border border-line",
    },
  };

  return (
    <div className="app-canvas flex min-h-screen flex-col">
      <header className="flex items-center justify-between px-4 py-4 sm:px-6">
        <Link href="/" className="flex items-center gap-2.5" aria-label="CampaignForge home">
          <span className="flex h-7 w-7 items-center justify-center rounded-md border border-accent bg-accent/10 text-accent-text">
            <Sparkles className="h-3.5 w-3.5" />
          </span>
          <span className="font-mono text-sm tracking-[0.15em] text-ink">CAMPAIGNFORGE</span>
        </Link>
        <ThemeToggle />
      </header>
      <main className="flex flex-1 flex-col items-center justify-center gap-6 px-4 pb-16">
        <div className="flex items-center gap-2 text-xs font-medium text-muted">
          <span aria-hidden className="h-px w-3.5 bg-accent" />
          {mode === "sign-in" ? "Welcome back" : "Create your workspace"}
        </div>
        <div className="motion-safe:animate-screen-in">
          {mode === "sign-in" ? <SignIn appearance={appearance} /> : <SignUp appearance={appearance} />}
        </div>
      </main>
    </div>
  );
}
