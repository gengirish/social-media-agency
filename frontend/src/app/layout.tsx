import type { Metadata } from "next";
import { IBM_Plex_Mono, Inter, Space_Grotesk } from "next/font/google";
import { ClerkProvider } from "@clerk/nextjs";
import { ClerkTokenSync } from "@/components/clerk-token-sync";
import { ThemedToaster } from "@/components/theme";
import { THEME_INIT_SCRIPT } from "@/lib/theme";
import "./globals.css";

const sans = Inter({ subsets: ["latin"], variable: "--font-sans", display: "swap" });
const display = Space_Grotesk({
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  variable: "--font-display",
  display: "swap",
});
const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "CampaignForge AI",
  description: "Your entire marketing team. One prompt away.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // suppressHydrationWarning: THEME_INIT_SCRIPT adds `dark` to <html> before
    // React hydrates, which is intentional and would otherwise warn.
    <html lang="en" suppressHydrationWarning className={`${sans.variable} ${display.variable} ${mono.variable}`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body className="font-sans scroll-smooth">
        {/*
          Post-auth landing is set here, not via env. Clerk v7 dropped
          NEXT_PUBLIC_CLERK_AFTER_SIGN_IN_URL entirely, so that variable is
          inert and sign-in falls back to "/" — the marketing page. Props also
          win over env, so this holds even where the removed vars are still set.
          Fallback, not force: middleware bounces a deep link like /analytics
          through /sign-in with ?redirect_url, and that should still be honored.
        */}
        <ClerkProvider
          signInFallbackRedirectUrl="/clients"
          signUpFallbackRedirectUrl="/clients"
          appearance={{ variables: { colorPrimary: "#F2C14E", colorTextOnPrimaryBackground: "#1A1406" } }}
        >
          <ClerkTokenSync />
          {children}
          <ThemedToaster />
        </ClerkProvider>
      </body>
    </html>
  );
}
