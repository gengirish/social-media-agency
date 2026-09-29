"use client";

import { memo, useEffect, useRef, useState, type ComponentType } from "react";
import Link from "next/link";
import { format, formatDistanceToNow, isValid, parseISO } from "date-fns";
import {
  AlertTriangle,
  BellRing,
  CalendarClock,
  Check,
  CheckCircle2,
  ChevronDown,
  ClipboardCheck,
  Copy,
  ExternalLink,
  Hand,
  Image as ImageIcon,
  Layers,
  Link2,
  Loader2,
  Palette,
  PenLine,
  RotateCcw,
  Send,
  Sparkles,
  Trash2,
  Video,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";
import { adVariantOf, unusableReason, type QueuePost } from "@/lib/api";
import { AdVariantCard } from "@/components/content/ad-variant-card";
import {
  BRIEF_ROWS,
  PLATFORM_LIMITS,
  creativeBriefOf,
  isOverdue,
  overdueLabel,
  renderedLength,
} from "@/lib/api-posts";
import {
  manualComposerUrl,
  manualPostText,
  prefillsBody,
  publishUnavailableReason,
  scheduleUnavailableReason,
} from "@/lib/platforms";
import { useSession } from "@/lib/session";
import { Button, buttonVariants } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/status-badge";
import { cn } from "@/lib/utils";
import { platformLabel, platformTone } from "./platform";

export type PostAction =
  | "approve"
  | "save"
  | "schedule"
  | "publish"
  | "regenerate"
  | "brief"
  | "retry"
  /** Recording a post a human made by hand — never publishing. */
  | "mark-posted"
  /** Attaching the link to an already-recorded hand-made post. */
  | "post-url";

/**
 * The client's manual, tokenless channel for this post's platform.
 *
 * `null` means the channel is OAuth-connected (or unregistered), and the card
 * keeps its normal Schedule / Publish now controls. When it is present the
 * product cannot post for this channel at all, so those controls are replaced
 * rather than added to.
 */
export interface ManualChannel {
  profileUrl: string | null;
}

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

/**
 * "Post it yourself" — the whole flow for a channel the product cannot post to.
 *
 * CampaignForge publishes nothing here, so no word on this panel may say
 * "publish" (product rule 1). One click puts the text on the clipboard and opens
 * the channel's composer; a second, deliberate step records that a human posted
 * it. Nothing is written or charged until that second step.
 */
function ManualPostActions({
  post,
  channel,
  busy,
  disabled,
  quotaReason,
  maySchedule,
  scheduling,
  onMarkPosted,
  onSchedule,
}: {
  post: QueuePost;
  channel: ManualChannel;
  busy: boolean;
  disabled: boolean;
  /** Why the plan cannot take another post, checked before a composer is opened. */
  quotaReason: string | null;
  /**
   * `publish.write`, not `publish.manual`.
   *
   * The server gates `POST /publishing/{id}/schedule` on `PUBLISH_WRITE` and nothing
   * about Phase 4 changed that, so a `member` — who holds `publish.manual` and can
   * record a post by hand — gets a 403 from the reminder endpoint. The button is
   * therefore hidden for them rather than offered and refused, which leaves a
   * `member` able to post and record but not to ask to be reminded.
   */
  maySchedule: boolean;
  scheduling: boolean;
  onMarkPosted: (post: QueuePost, postUrl: string | null) => void;
  onSchedule: (post: QueuePost) => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const [copied, setCopied] = useState(false);
  const [openedTab, setOpenedTab] = useState(false);
  const [link, setLink] = useState("");
  const label = platformLabel(post.platform);
  const prefilled = prefillsBody(post.platform);

  function start() {
    // Checked here rather than on confirm as well, so nobody composes into a tab
    // and only then learns the plan is full.
    if (quotaReason) {
      toast.error(quotaReason);
      return;
    }
    const text = manualPostText(post.body ?? "", post.hashtags ?? []);
    const url = manualComposerUrl(post.platform, {
      body: post.body ?? "",
      hashtags: post.hashtags ?? [],
      profileUrl: channel.profileUrl,
    });
    /*
     * ORDER IS LOAD-BEARING. The clipboard write and the window.open both happen
     * in this handler, synchronously, before any await: a popup opened after an
     * await has lost the user gesture and the browser blocks it.
     */
    let wrote = false;
    try {
      const p = navigator.clipboard?.writeText(text);
      if (p) {
        wrote = true;
        void p.catch(() => {
          setCopied(false);
          toast.error("Couldn't reach the clipboard — copy the post text from the card instead.");
        });
      }
    } catch {
      wrote = false;
    }
    if (url) window.open(url, "_blank", "noopener,noreferrer");
    setCopied(wrote);
    setOpenedTab(!!url);
    setConfirming(true);
  }

  if (!confirming) {
    return (
      <>
        <Button size="sm" onClick={start} disabled={disabled}>
          <Hand className="h-3.5 w-3.5" aria-hidden />
          Post it yourself
        </Button>
        {/*
          Phase 4's other half. The backend lets a manual piece be scheduled — the
          scheduler notifies and leaves it `scheduled`, never publishing it — and the
          card already words a scheduled manual piece as "Reminder around <time>", but
          until this button there was no way to reach any of it.

          Deliberately secondary to "Post it yourself": the reminder defers the work,
          it does not do it, and the piece still comes back through this same panel to
          be recorded. The label says "as a reminder" rather than "Schedule", because
          on a card that publishes nothing the bare word promises a send.
        */}
        {maySchedule && (
          <Button variant="secondary" size="sm" onClick={() => onSchedule(post)} disabled={disabled}>
            {scheduling ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <BellRing className="h-3.5 w-3.5" aria-hidden />
            )}
            {post.status === "scheduled" ? "Move the reminder" : "Schedule as a reminder"}
          </Button>
        )}
      </>
    );
  }

  return (
    <div className="w-full rounded-lg border border-line bg-panel/80 p-3 motion-safe:animate-screen-in">
      <p className="flex items-start gap-2 text-xs leading-snug text-slate-700" aria-live="polite">
        <ClipboardCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent-text" aria-hidden />
        <span>
          {prefilled && openedTab ? (
            <>
              Your post is <strong>prefilled</strong> in the {label} composer that just opened — check it there and
              post it. {copied ? "It's on your clipboard too." : ""}
            </>
          ) : openedTab ? (
            <>
              {copied ? "Copied" : "Copy the post text from the card"} — paste it into the {label} composer that just
              opened, then post it.
            </>
          ) : (
            <>
              {copied ? "Copied" : "Copy the post text from the card"} — open {label} yourself and paste it in. We
              have no verified composer link for {label}; add the page&apos;s address under Setup › Accounts and this
              will open it for you next time.
            </>
          )}
        </span>
      </p>
      <label className="mt-3 block space-y-1">
        <span className="text-xs font-medium text-muted">Link to the post (optional)</span>
        <input
          value={link}
          onChange={(e) => setLink(e.target.value)}
          placeholder="https://…"
          inputMode="url"
          className={cn(fieldClass, "border-line font-mono text-xs focus:border-accent")}
        />
      </label>
      <p className="mt-2 text-[11px] leading-snug text-muted">
        CampaignForge posted nothing — this only records that you did, and it counts one post against your plan. You
        can add the link later if you don&apos;t have it now.
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button size="sm" onClick={() => onMarkPosted(post, link.trim() || null)} disabled={busy}>
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
          {busy ? "Recording…" : "I posted it"}
        </Button>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => {
            setConfirming(false);
            setLink("");
          }}
          disabled={busy}
        >
          Cancel
        </Button>
        {/* "Schedule as a reminder" sits beside "Post it yourself" on the collapsed
            panel above, not here: once the composer is open the choice is record it or
            back out, and offering a future time in the middle of that is noise. */}
      </div>
    </div>
  );
}

/**
 * A hand-posted piece with no link on file: the honest state, plus a way out of it.
 *
 * Two rules meet here. Product rule 1 — the product posted nothing, so this may not
 * read as "Published". Product rule 4 — nothing here may stand a `0` in for a number
 * nobody has: there is no token for this page, so impressions and engagement are not
 * unknown-and-coming, they are unavailable, and the card says exactly that.
 *
 * The "Add link" affordance is permanent, not a one-time prompt. Someone who posted
 * from their phone may only have the link days later, and a prompt that expires would
 * leave the record wrong for good. It disappears only once a link is actually on file.
 */
function MissingPostLink({
  post,
  busy,
  mayEdit,
  onSetPostUrl,
}: {
  post: QueuePost;
  busy: boolean;
  /** `publish.manual` — the same capability the server requires on the PATCH. */
  mayEdit: boolean;
  onSetPostUrl: (post: QueuePost, postUrl: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [link, setLink] = useState("");

  return (
    <div className="mt-3 rounded-lg border border-line bg-canvas/40 p-3">
      <p className="flex items-start gap-2 text-xs leading-snug text-slate-700">
        <Hand className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted" aria-hidden />
        <span>Posted manually — no link, metrics unavailable</span>
      </p>
      <p className="mt-1.5 pl-[1.375rem] text-[11px] leading-snug text-muted">
        CampaignForge didn&apos;t post this and holds no access to the page, so it can&apos;t read impressions or
        engagement for it — and it won&apos;t show a zero instead. Adding the link doesn&apos;t change that; it makes
        the record complete and openable from here.
      </p>
      {mayEdit && !open && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="mt-2 ml-[1.375rem] inline-flex items-center gap-1 font-mono text-[10.5px] text-accent-text underline hover:no-underline"
        >
          <Link2 className="h-3 w-3" aria-hidden /> Add link
        </button>
      )}
      {mayEdit && open && (
        <form
          className="mt-2.5 space-y-2"
          onSubmit={(e) => {
            e.preventDefault();
            const value = link.trim();
            if (value) onSetPostUrl(post, value);
          }}
        >
          <label className="block space-y-1">
            <span className="text-xs font-medium text-muted">Link to the post</span>
            <input
              value={link}
              onChange={(e) => setLink(e.target.value)}
              placeholder="https://…"
              inputMode="url"
              autoFocus
              className={cn(fieldClass, "border-line font-mono text-xs focus:border-accent")}
            />
          </label>
          <div className="flex flex-wrap items-center gap-2">
            <Button type="submit" size="sm" disabled={busy || !link.trim()}>
              {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Link2 className="h-3.5 w-3.5" />}
              {busy ? "Saving…" : "Save link"}
            </Button>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => {
                setOpen(false);
                setLink("");
              }}
              disabled={busy}
            >
              Cancel
            </Button>
          </div>
        </form>
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
  /** Set when this post's channel is registered manually — see {@link ManualChannel}. */
  manual?: ManualChannel | null;
  /** Why the plan cannot take another post, or null. Pre-checked on the click that opens a composer. */
  quotaReason?: string | null;
  /** Record a post the user made by hand (`POST /publishing/{id}/mark-posted`). */
  onMarkPosted: (post: QueuePost, postUrl: string | null) => void;
  /** Attach the link to an already-recorded hand-made post (`PATCH /publishing/{id}/post-url`). */
  onSetPostUrl: (post: QueuePost, postUrl: string) => void;
  onDelete: (post: QueuePost) => void;
  /** Send a failed post back to Approved so publishing can be tried again (CF-06). */
  onRetry: (post: QueuePost) => void;
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
  manual,
  quotaReason = null,
  onMarkPosted,
  onSetPostUrl,
  onDelete,
  onRetry,
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
  // A separate capability: recording a post nobody's account was touched for is
  // bookkeeping, so a `member` holds it while `publish.write` stays owner/admin.
  const mayPostManually = can("publish.manual");
  const isManual = manual != null;

  const tone = platformTone(post.platform);
  const created = parse(post.created_at);
  const scheduledAt = parse(post.scheduled_at);
  const publishedAt = parse(post.published_at);
  const overdue = isOverdue(post, now);
  const blocked = publishUnavailableReason(post.platform);
  /*
   * Whether a time can be set at all, which is no longer the same question as
   * whether the product can publish. For a connected channel it still is — a
   * scheduled post there IS a publish, so this equals `blocked`. On a manual
   * channel the scheduler only ever notifies a human, so Instagram and TikTok,
   * which have no publisher, can still be given a reminder. `ensure_schedulable`
   * makes the same exception server-side.
   */
  const scheduleBlocked = scheduleUnavailableReason(post.platform, { manual: isManual });
  const postUrl = post.metadata_?.post_url;
  // A hand-made post: the product sent nothing, so the card must not say it published it.
  const manuallyPosted = post.metadata_?.publish_mode === "manual";
  const publishError = post.metadata_?.publish_error;
  const publishBlocked = post.metadata_?.publish_blocked;
  /*
   * A due reminder that nobody has confirmed. Read from the metadata rather than
   * from `isManual`, because the manual-channel map comes from a separate request
   * that can fail — and if it does, this notice must still appear: a piece the
   * scheduler has already refused to publish must never read as "will publish".
   */
  const reminderSentAt = parse(post.metadata_?.reminder_sent_at);
  const reminderAwaitingConfirm =
    post.status === "scheduled" && reminderSentAt !== null && reminderSentAt.getTime() <= now;
  // A scheduled piece on a manual channel is a reminder, not a job: the scheduler
  // notifies and leaves it alone (Phase 4), so no copy here may promise a publish.
  const isReminder = isManual || reminderSentAt !== null;
  const ad = adVariantOf(post);
  // Why this post cannot be approved, or null. Kept in step with the server's
  // `empty_content_reason` — the button is hidden here, refused there.
  const unusable = unusableReason(post);
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
            {isReminder ? (
              <>
                This reminder&apos;s time has passed. Nothing publishes it — this is a page you post yourself, so post
                it and then record it here with &ldquo;Post it yourself&rdquo;.
              </>
            ) : (
              <>
                This was due to publish and hasn&apos;t gone out. The scheduler checks every minute — if it stays here,
                publish it now or check the account under Setup › Accounts.
              </>
            )}
          </span>
        </div>
      )}

      {editing ? (
        <EditForm post={post} onSave={(edit) => onEditSave(post, edit)} onClose={onEditClose} />
      ) : (
        <>
          {post.title && <h3 className="mt-3 font-display text-base font-semibold text-ink">{post.title}</h3>}
          {/* An ad variant renders in its network's own fields (CF-03); only a
              social post is one body paragraph. */}
          {ad ? (
            <div className="mt-2">
              <AdVariantCard ad={ad} />
            </div>
          ) : (
            <p
              className={cn(
                "mt-1.5 line-clamp-6 whitespace-pre-wrap text-sm leading-relaxed",
                isDraft ? "text-muted" : "text-slate-700",
                busy === "regenerate" && "animate-pulse"
              )}
            >
              {post.body}
            </p>
          )}
          {!ad && unusable !== null && (
            <p className="mt-1.5 flex items-start gap-1.5 text-xs text-muted">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600" aria-hidden />
              {unusable} Regenerate it or delete it.
            </p>
          )}
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

      {/*
        A scheduled manual post is a reminder and nothing else — the scheduler sees
        it is due, notifies, and leaves it `scheduled`. "Publishes <time>" would be
        a straight falsehood there.

        "around", not "at", on purpose: the scheduler's wake interval is capped at up
        to an hour, so a 09:00 reminder can arrive at 09:59. The copy must not promise
        punctuality the scheduler does not deliver.
      */}
      {post.status === "scheduled" && scheduledAt && !overdue && (
        <p className="mt-3 flex items-center gap-1.5 text-xs text-muted">
          <CalendarClock className="h-3.5 w-3.5" aria-hidden />
          {isReminder ? (
            <>
              Reminder around <span className="font-mono">{format(scheduledAt, "EEE d MMM, HH:mm")}</span> — nothing
              goes out on its own; you post it yourself
            </>
          ) : (
            <>
              Publishes <span className="font-mono">{format(scheduledAt, "EEE d MMM, HH:mm")}</span>
            </>
          )}
        </p>
      )}

      {/*
        Reminded, still unconfirmed. The scheduler records `reminder_sent_at` once and
        then never touches the piece again, so without this it sits in Scheduled
        indefinitely looking like it is waiting its turn. Display only — no new status,
        and no call: confirming is still "Post it yourself" → "I posted it".
      */}
      {reminderAwaitingConfirm && reminderSentAt && (
        <p className="mt-2 flex items-start gap-1.5 text-xs text-muted">
          <BellRing className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600" aria-hidden />
          <span>
            Reminder sent{" "}
            <span className="font-mono" title={format(reminderSentAt, "PPpp")}>
              {formatDistanceToNow(reminderSentAt, { addSuffix: true })}
            </span>{" "}
            — not yet confirmed. If you have posted it, record it below; if you have not, it is still waiting on you.
          </span>
        </p>
      )}

      {post.status === "published" && (publishedAt || postUrl) && (
        <p className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
          {publishedAt && (
            <span className="flex items-center gap-1.5">
              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" aria-hidden />
              {manuallyPosted ? "Posted by hand" : "Published"}{" "}
              <span className="font-mono">{format(publishedAt, "EEE d MMM, HH:mm")}</span>
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

      {post.status === "published" && manuallyPosted && !postUrl && (
        <MissingPostLink
          post={post}
          busy={busy === "post-url"}
          mayEdit={mayPostManually}
          onSetPostUrl={onSetPostUrl}
        />
      )}

      {post.status === "failed" && (
        <div className="mt-3 flex gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">
          <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
          <p>{publishError ? `Publishing failed: ${publishError}` : "Publishing failed. The platform did not return a reason."}</p>
        </div>
      )}

      {/* CF-01: the post is fine — the workspace was not ready for it. It sits in
          Approved with its schedule cleared, rather than in Failed where the only
          action used to be Delete. */}
      {publishBlocked && post.status !== "published" && (
        <div className="mt-3 flex gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
          <p>{publishBlocked.reason}</p>
        </div>
      )}

      {!editing && post.status !== "published" && (
        <div className="mt-4 border-t border-line pt-3">
          {/* Irrelevant on a manual channel: nothing here was ever going to be
              published by the product, so "publishing isn't available yet" would
              be answering a question the card no longer asks. */}
          {mayPublish && !isManual && blocked && !isDraft && post.status !== "failed" && (
            <p className="mb-3 flex gap-2 text-xs text-amber-800">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
              {blocked}
            </p>
          )}
          <div className="flex flex-wrap items-center gap-2">
            {isDraft && (
              <>
                {/* CF-05: an item with nothing in it is not approvable — the
                    server refuses it with 409 empty_content, so offering the
                    button would only produce an error. Regenerate still shows,
                    which is the way out. */}
                {mayApprove && unusable === null && (
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

            {/*
              A manual channel has no tokens, so Publish now is replaced — not
              supplemented. It would fail server-side, and offering it would claim
              the product posts to a page it cannot reach. Scheduling survives, but
              as a reminder: `ManualPostActions` offers it in those words and the
              dialog, the "Reminder around <time>" line and the overdue notice all
              branch to match. The OAuth path below is untouched.
            */}
            {isManual && mayPostManually && (post.status === "approved" || post.status === "scheduled") && (
              <ManualPostActions
                post={post}
                channel={manual}
                busy={busy === "mark-posted"}
                disabled={anyBusy}
                quotaReason={quotaReason}
                maySchedule={mayPublish && scheduleBlocked === null}
                scheduling={busy === "schedule"}
                onMarkPosted={onMarkPosted}
                onSchedule={onSchedule}
              />
            )}

            {!isManual && mayPublish && (post.status === "approved" || post.status === "scheduled") && (
              <>
                <Button
                  size="sm"
                  variant={post.status === "approved" ? "primary" : "secondary"}
                  onClick={() => onSchedule(post)}
                  disabled={anyBusy || scheduleBlocked !== null}
                  title={scheduleBlocked ?? undefined}
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

            {/* CF-06: a failed post used to offer only Delete, so a transient
                publish failure meant rewriting the copy. Retry puts it back in
                Approved (re-moderated, since it may have been edited first), and
                Edit is available to fix whatever the platform rejected. */}
            {post.status === "failed" && mayApprove && (
              <Button size="sm" onClick={() => onRetry(post)} disabled={anyBusy}>
                {busy === "retry" ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <RotateCcw className="h-3.5 w-3.5" />
                )}
                {busy === "retry" ? "Checking…" : "Retry"}
              </Button>
            )}

            <Button variant="secondary" size="sm" onClick={() => onEditStart(post.id)} disabled={anyBusy}>
              <PenLine className="h-3.5 w-3.5" />
              {resumable ? "Resume edit" : "Edit"}
            </Button>

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
