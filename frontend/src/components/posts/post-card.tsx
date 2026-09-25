"use client";

import { memo, useEffect, useRef, useState, type ComponentType } from "react";
import Link from "next/link";
import { format, formatDistanceToNow, isValid, parseISO } from "date-fns";
import {
  AlertTriangle,
  CalendarClock,
  Check,
  CheckCircle2,
  ChevronDown,
  Copy,
  ExternalLink,
  Image as ImageIcon,
  Layers,
  Loader2,
  Palette,
  PenLine,
  Send,
  Sparkles,
  Trash2,
  Video,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";
import type { QueuePost } from "@/lib/api";
import {
  BRIEF_ROWS,
  PLATFORM_LIMITS,
  creativeBriefOf,
  isOverdue,
  overdueLabel,
  renderedLength,
} from "@/lib/api-posts";
import { publishUnavailableReason } from "@/lib/platforms";
import { useSession } from "@/lib/session";
import { Button, buttonVariants } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/status-badge";
import { cn } from "@/lib/utils";
import { platformLabel, platformTone } from "./platform";

export type PostAction = "approve" | "save" | "schedule" | "publish" | "regenerate" | "brief";

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

function sameEdit(a: PostEdit, b: PostEdit) {
  return a.title === b.title && a.body === b.body && a.hashtags.join(" ") === b.hashtags.join(" ");
}

/*
 * Local copy of an unfinished edit (Cadence's `draftContent`): an edit in
 * progress survives the card unmounting — tab switch, search, a reload —
 * without ever becoming the real post text until Save. Per-viewer only.
 */
const DRAFT_KEY = (id: string) => `cf-post-edit-${id}`;

export function readLocalEdit(id: string): PostEdit | null {
  try {
    const raw = window.localStorage.getItem(DRAFT_KEY(id));
    return raw ? (JSON.parse(raw) as PostEdit) : null;
  } catch {
    return null;
  }
}

function writeLocalEdit(id: string, edit: PostEdit | null) {
  try {
    if (edit) window.localStorage.setItem(DRAFT_KEY(id), JSON.stringify(edit));
    else window.localStorage.removeItem(DRAFT_KEY(id));
  } catch {
    // Blocked storage: the edit just isn't recoverable after unmount.
  }
}

const fieldClass =
  "w-full rounded-md border bg-panel px-3 py-2 text-sm text-ink outline-none transition-[border-color,box-shadow] duration-200 placeholder:text-slate-400 focus:shadow-[0_0_0_3px_rgb(var(--c-accent)/0.12)]";

type SaveState = "idle" | "saving" | "saved" | "error";

/**
 * Inline editor. Pending posts autosave to the server (debounced) — a draft
 * stays a draft, so nothing about the gate changes. Approved and scheduled
 * posts do NOT autosave there: saving their text sends them back to Pending
 * (PATCH semantics), so the edit is kept on this device until an explicit
 * "Save & send back to Pending".
 */
function EditForm({
  post,
  onSave,
  onClose,
}: {
  post: QueuePost;
  onSave: (edit: PostEdit) => Promise<void>;
  onClose: () => void;
}) {
  const original: PostEdit = {
    title: post.title ?? "",
    body: post.body ?? "",
    hashtags: post.hashtags ?? [],
  };
  const gated = post.status === "approved" || post.status === "scheduled";
  const [initial] = useState<PostEdit>(() => readLocalEdit(post.id) ?? original);
  const [title, setTitle] = useState(initial.title);
  const [body, setBody] = useState(initial.body);
  const [tags, setTags] = useState(initial.hashtags.map((t) => `#${t}`).join(" "));
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [committing, setCommitting] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastSaved = useRef<PostEdit>(original);
  const originalRef = useRef<PostEdit>(original);

  const current: PostEdit = { title: title.trim(), body, hashtags: parseHashtags(tags) };
  const limit = PLATFORM_LIMITS[post.platform?.toLowerCase()] ?? null;
  const length = renderedLength(body, current.hashtags);
  const overLimit = limit !== null && length > limit;

  async function flush(edit: PostEdit) {
    if (sameEdit(edit, lastSaved.current) || !edit.body.trim()) return;
    setSaveState("saving");
    try {
      await onSave(edit);
      lastSaved.current = edit;
      setSaveState("saved");
    } catch {
      setSaveState("error");
    }
  }

  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    if (gated) {
      // Kept locally only; the server copy changes on explicit Save.
      writeLocalEdit(post.id, sameEdit(current, originalRef.current) ? null : current);
      return;
    }
    timer.current = setTimeout(() => void flush(current), 800);
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
    // current is derived from these three; flush is stable enough for a debounce.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [title, body, tags]);

  async function done() {
    if (timer.current) clearTimeout(timer.current);
    if (!current.body.trim()) return;
    setCommitting(true);
    try {
      if (gated) {
        if (!sameEdit(current, originalRef.current)) await onSave(current);
      } else {
        await flush(current);
      }
      writeLocalEdit(post.id, null);
      onClose();
    } catch {
      // onSave already reported it; keep the editor open with the text intact.
    } finally {
      setCommitting(false);
    }
  }

  async function discard() {
    if (timer.current) clearTimeout(timer.current);
    writeLocalEdit(post.id, null);
    // Pending autosaves already reached the server — put the original back.
    if (!gated && !sameEdit(lastSaved.current, originalRef.current)) {
      setCommitting(true);
      try {
        await onSave(originalRef.current);
      } finally {
        setCommitting(false);
      }
    }
    onClose();
  }

  return (
    <form
      className="mt-3 space-y-3 motion-safe:animate-screen-in"
      onSubmit={(e) => {
        e.preventDefault();
        void done();
      }}
    >
      {gated && (
        <p className="flex gap-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600" aria-hidden />
          <span>
            Saving a change to the text or hashtags sends this post back to <strong>Pending</strong>: moderation
            checks it again and it needs a fresh approval
            {post.status === "scheduled" ? ", and its scheduled time is cleared" : ""}. Your edit is kept on this
            device until you save.
          </span>
        </p>
      )}
      <label className="block space-y-1">
        <span className="text-xs font-medium text-muted">Title</span>
        <input value={title} onChange={(e) => setTitle(e.target.value)} className={cn(fieldClass, "border-line focus:border-accent")} />
      </label>
      <label className="block space-y-1">
        <span className="text-xs font-medium text-muted">Post</span>
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          rows={Math.min(12, Math.max(4, body.split("\n").length + 1))}
          className={cn(fieldClass, "resize-y leading-relaxed", overLimit ? "border-red-400" : "border-accent")}
          autoFocus
        />
      </label>
      <label className="block space-y-1">
        <span className="text-xs font-medium text-muted">Hashtags</span>
        <input
          value={tags}
          onChange={(e) => setTags(e.target.value)}
          placeholder="#launch #b2b"
          className={cn(fieldClass, "border-line font-mono text-xs focus:border-accent")}
        />
      </label>
      <div className="flex flex-wrap items-center gap-2">
        <Button type="submit" size="sm" disabled={committing || !body.trim()}>
          {committing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
          {gated ? "Save & send back to Pending" : "Done"}
        </Button>
        <Button variant="secondary" size="sm" onClick={() => void discard()} disabled={committing}>
          {gated ? "Cancel" : "Discard changes"}
        </Button>
        <span className="font-mono text-[10.5px] text-muted" aria-live="polite">
          {!gated && saveState === "saving" && "Saving…"}
          {!gated && saveState === "saved" && "Saved — still Pending"}
          {!gated && saveState === "error" && <span className="text-red-600">Couldn&apos;t autosave — keep typing or press Done</span>}
        </span>
        <span className={cn("ml-auto font-mono text-[10.5px]", overLimit ? "text-red-600" : "text-muted")}>
          {length}
          {limit ? ` / ${limit}` : ""} chars{overLimit && ` — over ${platformLabel(post.platform)}'s limit`}
        </span>
      </div>
    </form>
  );
}

function BriefPanel({ post }: { post: QueuePost }) {
  const brief = creativeBriefOf(post);
  const [open, setOpen] = useState(false);
  if (!brief) return null;
  const text = BRIEF_ROWS.map(([k, label]) => `${label}: ${brief[k] ?? ""}`).join("\n");
  return (
    <div className="mt-3 rounded-lg border border-amber-300/60 bg-amber-50/60 p-3">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between font-mono text-[10.5px] uppercase tracking-wider text-accent-text"
      >
        <span className="flex items-center gap-1.5">
          <Palette className="h-3 w-3" aria-hidden /> Creative brief ready
        </span>
        <ChevronDown className={cn("h-3 w-3 transition-transform duration-200", open && "rotate-180")} aria-hidden />
      </button>
      {open && (
        <div className="mt-3 space-y-2 motion-safe:animate-screen-in">
          <p className="text-[11.5px] text-muted">
            A written brief for a designer. CampaignForge doesn&apos;t make or attach the image — the post goes out as
            text unless you add one where you publish it.
          </p>
          {BRIEF_ROWS.map(([key, label]) => (
            <div key={key}>
              <div className="font-mono text-[9px] uppercase tracking-wider text-muted">{label}</div>
              <div className="mt-px text-xs text-slate-600">{brief[key]}</div>
            </div>
          ))}
          <button
            type="button"
            onClick={() => {
              void navigator.clipboard
                ?.writeText(text)
                .then(() => toast.success("Brief copied"))
                .catch(() => toast.error("Couldn't copy — select the text instead"));
            }}
            className="inline-flex items-center gap-1 font-mono text-[10.5px] text-accent-text underline"
          >
            <Copy className="h-3 w-3" aria-hidden /> Copy brief
          </button>
        </div>
      )}
    </div>
  );
}

export interface PostCardProps {
  post: QueuePost;
  clientName: string | null;
  busy: PostAction | null;
  editing: boolean;
  now: number;
  removing?: boolean;
  selected?: boolean;
  onToggleSelect?: (id: string) => void;
  onApprove: (post: QueuePost) => void;
  onEditStart: (id: string) => void;
  onEditClose: () => void;
  onEditSave: (post: QueuePost, edit: PostEdit) => Promise<void>;
  onSchedule: (post: QueuePost) => void;
  onPublish: (post: QueuePost) => void;
  onDelete: (post: QueuePost) => void;
  onRegenerate: (post: QueuePost) => void;
  onCancelRegenerate: () => void;
  onRequestBrief: (post: QueuePost) => void;
  onCancelBrief: () => void;
}

/*
 * Memoized like Cadence's PostCard, so a "Writing for X…" tick during a batch
 * doesn't re-render every card — only effective because the page passes
 * stable callbacks.
 */
export const PostCard = memo(function PostCard({
  post,
  clientName,
  busy,
  editing,
  now,
  removing,
  selected,
  onToggleSelect,
  onApprove,
  onEditStart,
  onEditClose,
  onEditSave,
  onSchedule,
  onPublish,
  onDelete,
  onRegenerate,
  onCancelRegenerate,
  onRequestBrief,
  onCancelBrief,
}: PostCardProps) {
  /*
   * Presentation only — the server is the gate (`require_cap` in the routers).
   * An affordance is hidden rather than disabled: a button that 403s on click
   * is worse than an absent one. A `member` may approve but not publish, so
   * this card can legitimately show Approve and no Publish/Schedule.
   */
  const { can } = useSession();
  const mayApprove = can("content.approve");
  const mayPublish = can("publish.write");

  const tone = platformTone(post.platform);
  const created = parse(post.created_at);
  const scheduledAt = parse(post.scheduled_at);
  const publishedAt = parse(post.published_at);
  const overdue = isOverdue(post, now);
  const blocked = publishUnavailableReason(post.platform);
  const postUrl = post.metadata_?.post_url;
  const publishError = post.metadata_?.publish_error;
  const anyBusy = busy !== null;
  const isDraft = post.status === "draft";
  const needsVisual = post.platform?.toLowerCase() === "instagram";
  const hasBrief = creativeBriefOf(post) !== null;
  const resumable = !editing && typeof window !== "undefined" && readLocalEdit(post.id) !== null;
  const plannedFor = isDraft || post.status === "approved" ? scheduledAt : null;

  return (
    <article
      aria-busy={anyBusy}
      className={cn(
        "rounded-xl p-4 transition-[transform,box-shadow] duration-200 hover:-translate-y-0.5 sm:p-5",
        isDraft
          ? "border-[1.5px] border-dashed border-slate-300 bg-transparent"
          : "border border-line bg-panel/70 shadow-soft backdrop-blur-xl",
        selected && "ring-1 ring-accent/60",
        removing ? "animate-slide-out" : "motion-safe:animate-screen-in"
      )}
    >
      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5">
        {onToggleSelect && (
          <button
            type="button"
            onClick={() => onToggleSelect(post.id)}
            aria-label={selected ? "Deselect post" : "Select post"}
            aria-pressed={!!selected}
            className={cn(
              "flex h-4 w-4 shrink-0 items-center justify-center rounded border transition-colors",
              selected ? "border-accent bg-accent text-on-accent" : "border-slate-300"
            )}
          >
            {selected && <Check className="h-3 w-3" aria-hidden />}
          </button>
        )}
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
            <span className="inline-flex items-center gap-1 rounded-md border border-amber-300 bg-amber-50 px-2 py-0.5 font-mono text-[10.5px] font-medium text-amber-800">
              <AlertTriangle className="h-3 w-3" aria-hidden />
              {overdueLabel(post, now)}
            </span>
          )}
          <StatusBadge status={post.status} />
        </span>
      </div>

      {overdue && (
        <div className="mt-2 flex items-start gap-1.5 rounded-md border border-amber-300/60 bg-amber-50/60 px-2.5 py-2">
          <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-amber-600" aria-hidden />
          <span className="text-[11px] leading-snug text-slate-600">
            This was due to publish and hasn&apos;t gone out. The scheduler checks every minute — if it stays here,
            publish it now or check the account under Setup › Accounts.
          </span>
        </div>
      )}

      {editing ? (
        <EditForm post={post} onSave={(edit) => onEditSave(post, edit)} onClose={onEditClose} />
      ) : (
        <>
          {post.title && <h3 className="mt-3 font-display text-base font-semibold text-ink">{post.title}</h3>}
          <p
            className={cn(
              "mt-1.5 line-clamp-6 whitespace-pre-wrap text-sm leading-relaxed",
              isDraft ? "text-muted" : "text-slate-700",
              busy === "regenerate" && "animate-pulse"
            )}
          >
            {post.body}
          </p>
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

      {needsVisual && hasBrief && !editing && <BriefPanel post={post} />}

      {plannedFor && (
        <p className="mt-3 flex items-center gap-1.5 text-xs text-muted">
          <CalendarClock className="h-3.5 w-3.5" aria-hidden />
          Planned for <span className="font-mono">{format(plannedFor, "EEE d MMM")}</span>
          {isDraft ? (mayApprove ? " — approve it, then schedule it" : " — waiting on approval") : " — not scheduled yet"}
        </p>
      )}

      {post.status === "scheduled" && scheduledAt && !overdue && (
        <p className="mt-3 flex items-center gap-1.5 text-xs text-muted">
          <CalendarClock className="h-3.5 w-3.5" aria-hidden />
          Publishes <span className="font-mono">{format(scheduledAt, "EEE d MMM, HH:mm")}</span>
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

      {!editing && post.status !== "published" && (
        <div className="mt-4 border-t border-line pt-3">
          {mayPublish && blocked && !isDraft && post.status !== "failed" && (
            <p className="mb-3 flex gap-2 text-xs text-amber-800">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
              {blocked}
            </p>
          )}
          <div className="flex flex-wrap items-center gap-2">
            {isDraft && (
              <>
                {mayApprove && (
                  <Button size="sm" onClick={() => onApprove(post)} disabled={anyBusy}>
                    {busy === "approve" ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <CheckCircle2 className="h-3.5 w-3.5" />
                    )}
                    {busy === "approve" ? "Checking…" : "Approve"}
                  </Button>
                )}
                <Button variant="secondary" size="sm" onClick={() => onRegenerate(post)} disabled={anyBusy}>
                  {busy === "regenerate" ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Sparkles className="h-3.5 w-3.5" />
                  )}
                  {busy === "regenerate" ? "Rewriting…" : "Regenerate"}
                </Button>
                {busy === "regenerate" && (
                  <button type="button" onClick={onCancelRegenerate} className="font-mono text-[11px] text-muted underline hover:text-ink">
                    Cancel
                  </button>
                )}
              </>
            )}

            {mayPublish && (post.status === "approved" || post.status === "scheduled") && (
              <>
                <Button
                  size="sm"
                  variant={post.status === "approved" ? "primary" : "secondary"}
                  onClick={() => onSchedule(post)}
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
                  onClick={() => onPublish(post)}
                  disabled={anyBusy || blocked !== null}
                  title={blocked ?? undefined}
                >
                  {busy === "publish" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
                  Publish now
                </Button>
              </>
            )}

            {needsVisual && !hasBrief && post.status !== "failed" && (
              <>
                <Button variant="secondary" size="sm" onClick={() => onRequestBrief(post)} disabled={anyBusy}>
                  {busy === "brief" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Palette className="h-3.5 w-3.5" />}
                  {busy === "brief" ? "Directing…" : "Get creative brief"}
                </Button>
                {busy === "brief" && (
                  <button type="button" onClick={onCancelBrief} className="font-mono text-[11px] text-muted underline hover:text-ink">
                    Cancel
                  </button>
                )}
              </>
            )}

            {/*
              The brief is words for a human designer; these two would be the pixels.
              Neither is wired up in the Queue, so both are disabled and say so rather
              than being offered and failing -- the same rule as publishUnavailableReason.

              Note for whoever enables these: image generation already EXISTS server-side
              (POST /content/{id}/generate-image -> services/image_generation.py, fal.ai,
              live when FAL_API_KEY is set; it appends to content_piece.media_urls). It has
              no UI, no quota accounting and the card does not render media_urls, which is
              why it ships disabled here. Short-video generation has no backend at all.
            */}
            {needsVisual && post.status !== "failed" && (
              <>
                <ComingSoonAction icon={ImageIcon} label="Create image" />
                <ComingSoonAction icon={Video} label="Short video" />
              </>
            )}

            {post.status !== "failed" && (
              <Button variant="secondary" size="sm" onClick={() => onEditStart(post.id)} disabled={anyBusy}>
                <PenLine className="h-3.5 w-3.5" />
                {resumable ? "Resume edit" : "Edit"}
              </Button>
            )}

            <span className="ml-auto flex items-center gap-1">
              {isDraft && (
                <Link
                  href={`/amplify?source=${encodeURIComponent(post.id)}`}
                  className={buttonVariants({ variant: "ghost", size: "sm" })}
                >
                  <Layers className="h-3.5 w-3.5" />
                  Amplify
                </Link>
              )}
              <button
                type="button"
                onClick={() => onDelete(post)}
                disabled={anyBusy}
                aria-label="Delete this post"
                title="Delete"
                className="press-scale rounded-md p-1.5 text-muted transition-colors hover:bg-red-50 hover:text-red-600 disabled:opacity-40"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </span>
          </div>
        </div>
      )}
    </article>
  );
});

/**
 * A visual-generation action the Queue cannot perform yet. Rendered disabled with
 * a "Soon" tag so the card shows the intended shape of the feature without ever
 * implying it will produce an image or a video today.
 */
function ComingSoonAction({
  icon: Icon,
  label,
}: {
  icon: ComponentType<{ className?: string }>;
  label: string;
}) {
  return (
    <Button
      variant="secondary"
      size="sm"
      disabled
      aria-disabled
      title={`${label} — coming soon. Not available yet.`}
      className="cursor-not-allowed"
    >
      <Icon className="h-3.5 w-3.5" aria-hidden />
      {label}
      <span className="ml-1 rounded-full border border-line px-1.5 py-px font-mono text-[9.5px] uppercase tracking-wide text-muted">
        Soon
      </span>
    </Button>
  );
}
