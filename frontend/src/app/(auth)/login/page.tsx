"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Sparkles, Zap, BarChart3, Users } from "lucide-react";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await api.login(email, password);
      localStorage.setItem("token", res.access_token);
      localStorage.setItem("org_id", res.org_id);
      router.push("/campaigns");
    } catch (err: any) {
      toast.error(err.message || "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen">
      {/* Left — Branding */}
      <div className="hidden lg:flex lg:w-1/2 flex-col justify-between bg-gradient-to-br from-indigo-600 via-indigo-700 to-purple-800 p-12 text-white">
        <div>
          <div className="flex items-center gap-3">
            <Sparkles className="h-8 w-8" />
            <h1 className="text-2xl font-bold">CampaignForge AI</h1>
          </div>
          <p className="mt-2 text-indigo-200">Multi-Agent Digital Marketing Agency</p>
        </div>

        <div className="space-y-8">
          <h2 className="text-4xl font-bold leading-tight">
            Your entire marketing team.
            <br />
            <span className="text-indigo-300">One prompt away.</span>
          </h2>

          <div className="grid grid-cols-2 gap-6">
            <div className="rounded-xl bg-white/10 p-4 backdrop-blur">
              <Zap className="mb-2 h-6 w-6 text-yellow-300" />
              <h3 className="font-semibold">7 AI Agents</h3>
              <p className="mt-1 text-sm text-indigo-200">Strategy, SEO, Content, Ads, QA — all automated</p>
            </div>
            <div className="rounded-xl bg-white/10 p-4 backdrop-blur">
              <BarChart3 className="mb-2 h-6 w-6 text-emerald-300" />
              <h3 className="font-semibold">10x Faster</h3>
              <p className="mt-1 text-sm text-indigo-200">Full campaign in minutes, not weeks</p>
            </div>
            <div className="rounded-xl bg-white/10 p-4 backdrop-blur">
              <Users className="mb-2 h-6 w-6 text-pink-300" />
              <h3 className="font-semibold">Multi-Client</h3>
              <p className="mt-1 text-sm text-indigo-200">Manage unlimited brands from one dashboard</p>
            </div>
            <div className="rounded-xl bg-white/10 p-4 backdrop-blur">
              <Sparkles className="mb-2 h-6 w-6 text-orange-300" />
              <h3 className="font-semibold">€199/mo</h3>
              <p className="mt-1 text-sm text-indigo-200">vs €5,000/mo agency retainer</p>
            </div>
          </div>
        </div>

        <p className="text-sm text-indigo-300">© 2026 CampaignForge AI — Powered by LangGraph</p>
      </div>

      {/* Right — Login Form */}
      <div className="flex w-full items-center justify-center p-8 lg:w-1/2">
        <div className="w-full max-w-md space-y-8">
          <div className="text-center lg:text-left">
            <div className="mb-2 flex items-center justify-center gap-2 lg:hidden">
              <Sparkles className="h-6 w-6 text-indigo-600" />
              <h1 className="text-xl font-bold text-slate-900">CampaignForge AI</h1>
            </div>
            <h2 className="text-2xl font-bold text-slate-900">Welcome back</h2>
            <p className="mt-1 text-slate-500">Sign in to your agency dashboard</p>
          </div>

          <form onSubmit={handleLogin} className="space-y-5">
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="admin@campaignforge.ai"
                required
                className="w-full rounded-lg border border-slate-300 px-4 py-2.5 text-slate-900 placeholder-slate-400 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                required
                className="w-full rounded-lg border border-slate-300 px-4 py-2.5 text-slate-900 placeholder-slate-400 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-lg bg-indigo-600 px-6 py-2.5 font-semibold text-white transition-colors hover:bg-indigo-500 disabled:opacity-50"
            >
              {loading ? "Signing in..." : "Sign In"}
            </button>
          </form>

          <p className="text-center text-sm text-slate-500">
            Demo: admin@campaignforge.ai / password123
          </p>
        </div>
      </div>
    </div>
  );
}
