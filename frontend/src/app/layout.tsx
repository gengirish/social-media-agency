import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { ClerkProvider } from "@clerk/nextjs";
import { Toaster } from "sonner";
import { ClerkTokenSync } from "@/components/clerk-token-sync";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "CampaignForge AI",
  description: "Your entire marketing team. One prompt away.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${inter.className} scroll-smooth`}>
        {/*
          Post-auth landing is set here, not via env. Clerk v7 dropped
          NEXT_PUBLIC_CLERK_AFTER_SIGN_IN_URL entirely, so that variable is
          inert and sign-in falls back to "/" — the marketing page. Props also
          win over env, so this holds even where the removed vars are still set.
          Fallback, not force: middleware bounces a deep link like /analytics
          through /sign-in with ?redirect_url, and that should still be honored.
        */}
        <ClerkProvider
          signInFallbackRedirectUrl="/campaigns"
          signUpFallbackRedirectUrl="/campaigns"
        >
          <ClerkTokenSync />
          {children}
          <Toaster position="top-right" richColors />
        </ClerkProvider>
      </body>
    </html>
  );
}
