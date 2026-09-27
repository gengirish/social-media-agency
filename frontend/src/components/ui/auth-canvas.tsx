"use client";

import Link from "next/link";
import { SignIn, SignUp } from "@clerk/nextjs";
import { Sparkles } from "lucide-react";
import { ThemeToggle, useTheme } from "@/components/theme";
import { clerkVariables } from "@/lib/clerk-appearance";

export function AuthCanvas({ mode }: { mode: "sign-in" | "sign-up" }) {
  const theme = useTheme();
  const appearance = {
    variables: clerkVariables(theme),
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
