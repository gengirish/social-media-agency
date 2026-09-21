"use client";

import { useState } from "react";
import Link from "next/link";
import { format, formatDistanceToNow, isValid, parseISO } from "date-fns";
import {
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  Clock,
  ExternalLink,
  Layers,
  Loader2,
  Pencil,
  Send,
  XCircle,
} from "lucide-react";
import type { QueuePost } from "@/lib/api";
import { publishUnavailableReason } from "@/lib/platforms";
import { Button, buttonVariants } from "@/components/ui/button";
import { Panel } from "@/components/ui/panel";
import { StatusBadge } from "@/components/ui/status-badge";
import { cn } from "@/lib/utils";
import { platformLabel, platformTone } from "./platform";

export type PostAction = "approve" | "save" | "schedule" | "publish";

export interface PostEdit {
  title: string;
  body: string;
  hashtags: string[];
}

function parse(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const d = parseISO(iso);
  return isValid(d) ? d : null;
}

function parseHashtags(raw: string): string[] {
  return raw
    .split(/[\s,]+/)
    .map((t) => t.replace(/^#+/, "").trim())
    .filter(Boolean);
}

const fieldClass =
  "w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink outline-none transition-colors placeholder:text-slate-400 focus:border-accent";

function EditForm({
  post,
  saving,
  onSave,
  onCancel,
}: {
  post: QueuePost;
  saving: boolean;
  onSave: (edit: PostEdit) => void;
  onCancel: () => void;
}) {
  const [title, setTitle] = useState(post.title ?? "");
  const [body, setBody] = useState(post.body ?? "");
  const [tags, setTags] = useState((post.hashtags ?? []).map((t) => `#${t}`).join(" "));

  return (
    <form
      className="mt-3 space-y-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (!body.trim()) return;
        onSave({ title: title.trim(), body, hashtags: parseHashtags(tags) });
      }}
    >
      <label className="block space-y-1">
        <span className="text-xs font-medium text-muted">Title</span>
        <input value={title} onChange={(e) => setTitle(e.target.value)} className={fieldClass} />
      </label>
      <label className="block space-y-1">
        <span className="flex justify-between text-xs font-medium text-muted">
          Post
          <span className="font-mono text-[11px]">{body.length} chars</span>
        </span>
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          rows={Math.min(12, Math.max(4, body.split("\n").length + 1))}
          className={cn(fieldClass, "resize-y leading-relaxed")}
          autoFocus
        />
      </label>
      <label className="block space-y-1">
        <span className="text-xs font-medium text-muted">Hashtags</span>
        <input
          value={tags}
          onChange={(e) => setTags(e.target.value)}
          placeholder="#launch #b2b"
          className={cn(fieldClass, "font-mono text-xs")}
        />
      </label>
      <div className="flex flex-wrap items-center gap-2">
        <Button type="submit" size="sm" disabled={saving || !body.trim()}>
          {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          Save changes
        </Button>
        <Button variant="ghost" size="sm" onClick={onCancel} disabled={saving}>
          Cancel
        </Button>
        <span className="text-xs text-muted">Still Pending after saving — approve runs moderation on the new text.</span>
      </div>
    </form>
  );
}

export function PostCard({
  post,
  clientName,
  busy,
  editing,
  now,
  onApprove,
  onEditStart,
  onEditCancel,
  onEditSave,
  onSchedule,
  onPublish,
}: {
  post: QueuePost;
  clientName: string | null;
  busy: PostAction | null;
  editing: boolean;
  now: number;
  onApprove: () => void;
  onEditStart: () => void;
  onEditCancel: () => void;
  onEditSave: (edit: PostEdit) => void;
  onSchedule: () => void;
  onPublish: () => void;
}) {
  const tone = platformTone(post.platform);
  const created = parse(post.created_at);
  const scheduledAt = parse(post.scheduled_at);
  const publishedAt = parse(post.published_at);
  const overdue = post.status === "scheduled" && scheduledAt !== null && scheduledAt.getTime() < now;
  const blocked = publishUnavailableReason(post.platform);
  const postUrl = post.metadata_?.post_url;
  const publishError = post.metadata_?.publish_error;
  const anyBusy = busy !== null;

  return (
    <Panel className="p-4 sm:p-5" aria-busy={anyBusy}>
      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5">
        <span
          className={cn(
            "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium",
            tone.chip
          )}
        >
          <span aria-hidden className={cn("h-1.5 w-1.5 rounded-full", tone.dot)} />
          {platformLabel(post.platform)}
        </span>
        {clientName && <span className="text-xs font-medium text-ink">{clientName}</span>}
        {created && (
          <span className="font-mono text-[11px] text-muted" title={format(created, "PPpp")}>
            {formatDistanceToNow(created, { addSuffix: true })}
          </span>
        )}
        <span className="ml-auto flex items-center gap-1.5">
          {overdue && (
            <span className="inline-flex items-center gap-1 rounded-full border border-red-200 bg-red-50 px-2 py-0.5 font-mono text-[11px] font-medium text-red-700">
              <Clock className="h-3 w-3" aria-hidden />
              Overdue
            </span>
          )}
          <StatusBadge status={post.status} />
        </span>
      </div>

      {editing ? (
        <EditForm post={post} saving={busy === "save"} onSave={onEditSave} onCancel={onEditCancel} />
      ) : (
        <>
          {post.title && <h3 className="mt-3 font-display text-base font-semibold text-ink">{post.title}</h3>}
          <p className="mt-1.5 line-clamp-5 whitespace-pre-wrap text-sm leading-relaxed text-slate-700">{post.body}</p>
          {post.hashtags?.length > 0 && (
            <div className="mt-2.5 flex flex-wrap gap-x-2 gap-y-1">
              {post.hashtags.map((tag, i) => (
                <span key={i} className="font-mono text-xs text-accent-text">
                  #{tag}
                </span>
              ))}
            </div>
          )}
        </>
      )}

      {post.status === "scheduled" && scheduledAt && (
        <p className={cn("mt-3 flex items-center gap-1.5 text-xs", overdue ? "text-red-700" : "text-muted")}>
          <CalendarClock className="h-3.5 w-3.5" aria-hidden />
          {overdue ? "Was due " : "Publishes "}
          <span className="font-mono">{format(scheduledAt, "EEE d MMM, HH:mm")}</span>
          {overdue && " — not published yet"}
        </p>
      )}

      {post.status === "published" && (publishedAt || postUrl) && (
        <p className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
          {publishedAt && (
            <span className="flex items-center gap-1.5">
              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" aria-hidden />
              Published <span className="font-mono">{format(publishedAt, "EEE d MMM, HH:mm")}</span>
            </span>
          )}
          {postUrl && (
            <a
              href={postUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 font-medium text-accent-text hover:underline"
            >
              View post <ExternalLink className="h-3 w-3" />
            </a>
          )}
        </p>
      )}

      {post.status === "failed" && (
        <div className="mt-3 flex gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">
          <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
          <p>{publishError ? `Publishing failed: ${publishError}` : "Publishing failed. The platform did not return a reason."}</p>
        </div>
      )}

      {!editing && (post.status === "draft" || post.status === "approved" || post.status === "scheduled") && (
        <div className="mt-4 border-t border-line pt-3">
          {blocked && post.status !== "draft" && (
            <p className="mb-3 flex gap-2 text-xs text-amber-800">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
              {blocked}
            </p>
          )}
          <div className="flex flex-wrap items-center gap-2">
            {post.status === "draft" && (
              <>
                <Button size="sm" onClick={onApprove} disabled={anyBusy}>
                  {busy === "approve" ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <CheckCircle2 className="h-3.5 w-3.5" />
                  )}
                  {busy === "approve" ? "Checking…" : "Approve"}
                </Button>
                <Button variant="secondary" size="sm" onClick={onEditStart} disabled={anyBusy}>
                  <Pencil className="h-3.5 w-3.5" />
                  Edit
                </Button>
                <Link
                  href={`/amplify?source=${encodeURIComponent(post.id)}`}
                  className={cn(buttonVariants({ variant: "ghost", size: "sm" }), "sm:ml-auto")}
                >
                  <Layers className="h-3.5 w-3.5" />
                  Amplify
                </Link>
              </>
            )}

            {(post.status === "approved" || post.status === "scheduled") && (
              <>
                <Button
                  size="sm"
                  variant={post.status === "approved" ? "primary" : "secondary"}
                  onClick={onSchedule}
                  disabled={anyBusy || blocked !== null}
                  title={blocked ?? undefined}
                >
                  {busy === "schedule" ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <CalendarClock className="h-3.5 w-3.5" />
                  )}
                  {post.status === "approved" ? "Schedule" : "Reschedule"}
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={onPublish}
                  disabled={anyBusy || blocked !== null}
                  title={blocked ?? undefined}
                >
                  {busy === "publish" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
                  Publish now
                </Button>
              </>
            )}
          </div>
        </div>
      )}
    </Panel>
  );
}
