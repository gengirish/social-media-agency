"use client";

import { useEffect, useState } from "react";
import { api, type ContentPiece } from "@/lib/api";
import { toast } from "sonner";
import { Loader2, FileText, CheckCircle2, Filter } from "lucide-react";
import { cn } from "@/lib/utils";

const PLATFORM_COLORS: Record<string, string> = {
  linkedin: "bg-indigo-50 text-indigo-700",
  twitter: "bg-sky-50 text-sky-700",
  instagram: "bg-pink-50 text-pink-700",
  facebook: "bg-blue-50 text-blue-700",
  tiktok: "bg-slate-50 text-slate-700",
  google: "bg-red-50 text-red-700",
  meta: "bg-blue-50 text-blue-700",
};

const STATUS_COLORS: Record<string, string> = {
  draft: "bg-slate-100 text-slate-700",
  approved: "bg-emerald-100 text-emerald-700",
  scheduled: "bg-indigo-100 text-indigo-700",
  published: "bg-green-100 text-green-700",
};

export default function ContentPage() {
  const [content, setContent] = useState<ContentPiece[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>("");

  useEffect(() => {
    loadContent();
  }, [filter]);

  function loadContent() {
    const params: Record<string, string> = {};
    if (filter) params.status = filter;
    api.getContent(params)
      .then((res) => setContent(res.items))
      .catch((err) => toast.error(err.message))
      .finally(() => setLoading(false));
  }

  if (loading) {
    return <div className="flex h-64 items-center justify-center"><Loader2 className="h-8 w-8 animate-spin text-indigo-600" /></div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Content Library</h1>
          <p className="mt-1 text-slate-500">All AI-generated content across campaigns</p>
        </div>
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-slate-400" />
          <select
            value={filter}
            onChange={(e) => { setFilter(e.target.value); setLoading(true); }}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-indigo-500"
          >
            <option value="">All Status</option>
            <option value="draft">Draft</option>
            <option value="approved">Approved</option>
            <option value="scheduled">Scheduled</option>
            <option value="published">Published</option>
          </select>
        </div>
      </div>

      {content.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-200 py-16">
          <FileText className="mb-4 h-12 w-12 text-slate-300" />
          <h3 className="text-lg font-semibold text-slate-900">No content yet</h3>
          <p className="mt-1 text-slate-500">Run a campaign to generate content</p>
        </div>
      ) : (
        <div className="space-y-4">
          {content.map((piece) => (
            <div key={piece.id} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className={cn("rounded-full px-2.5 py-0.5 text-xs font-medium", PLATFORM_COLORS[piece.platform])}>
                    {piece.platform}
                  </span>
                  <span className="text-xs text-slate-400">{piece.content_type}</span>
                  <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", STATUS_COLORS[piece.status])}>
                    {piece.status}
                  </span>
                </div>
                {piece.status === "draft" && (
                  <button
                    onClick={async () => { await api.approveContent(piece.id); loadContent(); toast.success("Approved!"); }}
                    className="flex items-center gap-1 rounded-lg bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-700 hover:bg-emerald-100"
                  >
                    <CheckCircle2 className="h-3.5 w-3.5" /> Approve
                  </button>
                )}
              </div>
              {piece.title && <h3 className="mt-3 font-semibold text-slate-900">{piece.title}</h3>}
              <p className="mt-2 whitespace-pre-wrap text-sm text-slate-700 line-clamp-4">{piece.body}</p>
              {piece.hashtags?.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1">
                  {piece.hashtags.map((tag, i) => <span key={i} className="text-xs text-indigo-600">#{tag}</span>)}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
