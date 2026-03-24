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
      <body className={inter.className}>
        <ClerkProvider>
          <ClerkTokenSync />
          {children}
          <Toaster position="top-right" richColors />
        </ClerkProvider>
      </body>
    </html>
  );
}
