"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { UserButton } from "@clerk/nextjs";
import { cn } from "@/lib/utils";
import {
  Sparkles,
  LayoutDashboard,
  Users,
  Megaphone,
  FileText,
  BarChart3,
  Settings,
  Menu,
  Calendar,
  CreditCard,
} from "lucide-react";
import { useState } from "react";

const navItems = [
  { label: "Overview", href: "/campaigns", icon: LayoutDashboard },
  { label: "Clients", href: "/clients", icon: Users },
  { label: "Campaigns", href: "/campaigns", icon: Megaphone },
  { label: "Content Library", href: "/content", icon: FileText },
  { label: "Calendar", href: "/calendar", icon: Calendar },
  { label: "Team", href: "/team", icon: Users },
  { label: "Pricing", href: "/pricing", icon: CreditCard },
  { label: "Analytics", href: "/analytics", icon: BarChart3 },
  { label: "Settings", href: "/settings", icon: Settings },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const sidebar = (
    <div className="flex h-full flex-col bg-white border-r border-slate-200">
      <div className="flex h-16 items-center gap-3 px-6 border-b border-slate-100">
        <Sparkles className="h-6 w-6 text-indigo-600" />
        <span className="text-lg font-bold text-slate-900">CampaignForge</span>
      </div>

      <nav className="flex-1 space-y-1 px-3 py-4">
        {navItems.map((item) => {
          const active = pathname === item.href || pathname.startsWith(item.href + "/");
          return (
            <Link
              key={item.href + item.label}
              href={item.href}
              onClick={() => setSidebarOpen(false)}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                active
                  ? "bg-indigo-50 text-indigo-700"
                  : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
              )}
            >
              <item.icon className="h-5 w-5" />
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-slate-100 p-3">
        <div className="flex items-center gap-3 px-3 py-2">
          <UserButton />
          <span className="text-sm text-slate-600">Account</span>
        </div>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-indigo-50/30">
      <div className="hidden lg:fixed lg:inset-y-0 lg:flex lg:w-64">{sidebar}</div>

      {sidebarOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-black/50" onClick={() => setSidebarOpen(false)} />
          <div className="absolute inset-y-0 left-0 w-64">{sidebar}</div>
        </div>
      )}

      <div className="lg:pl-64">
        <header className="sticky top-0 z-40 flex h-16 items-center gap-4 border-b border-slate-200 bg-white/80 px-4 backdrop-blur sm:px-6 lg:px-8">
          <button onClick={() => setSidebarOpen(true)} className="lg:hidden">
            <Menu className="h-6 w-6 text-slate-600" />
          </button>
          <div className="flex-1" />
          <UserButton />
        </header>

        <main className="p-4 sm:p-6 lg:p-8">{children}</main>
      </div>
    </div>
  );
}
