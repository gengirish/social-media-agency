"use client";

import { useEffect, useState } from "react";
import { api, type ContentPiece } from "@/lib/api";
import { toast } from "sonner";
import { Loader2, FileText, CheckCircle2, Filter, Send, Layers, X } from "lucide-react";
import { cn } from "@/lib/utils";

const REPURPOSE_PLATFORMS = [
  { id: "linkedin", label: "LinkedIn" },
  { id: "twitter", label: "X (Twitter)" },
  { id: "instagram", label: "Instagram" },
  { id: "facebook", label: "Facebook" },
  { id: "tiktok", label: "TikTok" },
] as const;

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
  const [repurposePiece, setRepurposePiece] = useState<ContentPiece | null>(null);
  const [repurposeTargets, setRepurposeTargets] = useState<string[]>([]);
  const [repurposeBusy, setRepurposeBusy] = useState(false);
  const [publishBusyId, setPublishBusyId] = useState<string | null>(null);

  useEffect(() => {
    loadContent();
  }, [filter]);

  function loadContent() {
    const params: Record<string, string> = {};
    if (filter) params.status = filter;
    api
      .getContent(params)
      .then((res) => setContent(res.items))
      .catch((err: Error) => toast.error(err.message))
      .finally(() => setLoading(false));
  }

  function openRepurpose(piece: ContentPiece) {
    const current = (piece.platform ?? "").toLowerCase();
    setRepurposeTargets(
      REPURPOSE_PLATFORMS.map((p) => p.id).filter((id) => id !== current)
    );
    setRepurposePiece(piece);
  }

  async function runRepurpose() {
    if (!repurposePiece || repurposeTargets.length === 0) {
      toast.error("Select at least one target platform");
      return;
    }
    setRepurposeBusy(true);
    try {
      const res = await api.repurposeContent(repurposePiece.id, repurposeTargets);
      toast.success(`Repurposed to ${res.count} platform(s)`);
      setRepurposePiece(null);
      loadContent();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Repurpose failed");
    } finally {
      setRepurposeBusy(false);
    }
  }

  async function publishNow(piece: ContentPiece) {
    setPublishBusyId(piece.id);
    try {
      await api.publishContent(piece.id);
      toast.success("Publish requested");
      loadContent();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Publish failed");
    } finally {
      setPublishBusyId(null);
    }
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
                  <span
                    className={cn(
                      "rounded-full px-2.5 py-0.5 text-xs font-medium",
                      PLATFORM_COLORS[piece.platform?.toLowerCase?.() ?? ""] ?? "bg-slate-50 text-slate-700"
                    )}
                  >
                    {piece.platform}
                  </span>
                  <span className="text-xs text-slate-400">{piece.content_type}</span>
                  <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", STATUS_COLORS[piece.status])}>
                    {piece.status}
                  </span>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {piece.status === "draft" && (
                    <button
                      type="button"
                      onClick={async () => {
                        await api.approveContent(piece.id);
                        loadContent();
                        toast.success("Approved!");
                      }}
                      className="flex items-center gap-1 rounded-lg bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-700 hover:bg-emerald-100"
                    >
                      <CheckCircle2 className="h-3.5 w-3.5" /> Approve
                    </button>
                  )}
                  {piece.status === "approved" && (
                    <button
                      type="button"
                      disabled={publishBusyId === piece.id}
                      onClick={() => publishNow(piece)}
                      className="flex items-center gap-1 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
                    >
                      {publishBusyId === piece.id ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Send className="h-3.5 w-3.5" />
                      )}
                      Publish Now
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => openRepurpose(piece)}
                    className="flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
                  >
                    <Layers className="h-3.5 w-3.5" />
                    Repurpose
                  </button>
                </div>
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

      {repurposePiece && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <button
            type="button"
            className="absolute inset-0 bg-black/40"
            aria-label="Close repurpose dialog"
            onClick={() => !repurposeBusy && setRepurposePiece(null)}
          />
          <div className="relative z-10 w-full max-w-md rounded-xl border border-slate-200 bg-white p-6 shadow-xl">
            <button
              type="button"
              disabled={repurposeBusy}
              onClick={() => setRepurposePiece(null)}
              className="absolute right-4 top-4 rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 disabled:opacity-50"
            >
              <X className="h-5 w-5" />
            </button>
            <h2 className="text-lg font-bold text-slate-900">Repurpose content</h2>
            <p className="mt-1 text-sm text-slate-500">
              Create variants for other platforms from &ldquo;{repurposePiece.title || "this post"}&rdquo;.
            </p>
            <div className="mt-4 space-y-2">
              {REPURPOSE_PLATFORMS.filter(
                (p) => p.id !== (repurposePiece.platform ?? "").toLowerCase()
              ).map((p) => (
                <label
                  key={p.id}
                  className="flex cursor-pointer items-center gap-3 rounded-lg border border-slate-100 px-3 py-2 hover:bg-slate-50"
                >
                  <input
                    type="checkbox"
                    className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                    checked={repurposeTargets.includes(p.id)}
                    onChange={(e) => {
                      setRepurposeTargets((prev) =>
                        e.target.checked ? [...prev, p.id] : prev.filter((x) => x !== p.id)
                      );
                    }}
                  />
                  <span className="text-sm font-medium text-slate-800">{p.label}</span>
                </label>
              ))}
            </div>
            <div className="mt-6 flex justify-end gap-2">
              <button
                type="button"
                disabled={repurposeBusy}
                onClick={() => setRepurposePiece(null)}
                className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={repurposeBusy || repurposeTargets.length === 0}
                onClick={() => runRepurpose()}
                className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                {repurposeBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Layers className="h-4 w-4" />}
                Repurpose
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
