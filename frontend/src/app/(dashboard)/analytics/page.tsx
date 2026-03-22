"use client";

import { BarChart3, TrendingUp, Clock } from "lucide-react";

export default function AnalyticsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Analytics</h1>
        <p className="mt-1 text-slate-500">Campaign performance and insights</p>
      </div>

      <div className="flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-200 py-20">
        <BarChart3 className="mb-4 h-16 w-16 text-slate-200" />
        <h3 className="text-lg font-semibold text-slate-900">Coming Soon</h3>
        <p className="mt-2 max-w-md text-center text-slate-500">
          Analytics will be populated after campaigns are published and performance data is collected from connected platforms.
        </p>
        <div className="mt-6 flex gap-6 text-sm text-slate-400">
          <div className="flex items-center gap-1"><TrendingUp className="h-4 w-4" /> Engagement Tracking</div>
          <div className="flex items-center gap-1"><BarChart3 className="h-4 w-4" /> ROI Reports</div>
          <div className="flex items-center gap-1"><Clock className="h-4 w-4" /> Real-time Metrics</div>
        </div>
      </div>
    </div>
  );
}
