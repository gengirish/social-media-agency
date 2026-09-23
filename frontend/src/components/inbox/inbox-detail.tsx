"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  CheckCircle2,
  Copy,
  ExternalLink,
  Loader2,
  Send,
  Sparkle,
} from "lucide-react";
import { toast } from "sonner";
import { ApiError, apiErrorStatus, isGenerationQuotaError } from "@/lib/api";
import {
  inboxApi,
  type InboxAccount,
  type InboxItem,
  type ModerationIssue,
  type ReplySuggestion,
} from "@/lib/api-inbox";
import { trackFeature } from "@/lib/analytics";
import { platformLabel } from "@/components/posts/platform";
import { PostDialog } from "@/components/posts/dialog";
import { Button } from "@/components/ui/button";
import { ErrorBanner } from "@/components/ui/feedback";
import { QuotaHint } from "@/components/ui/quota-hint";
import { cn } from "@/lib/utils";
import { PlatformGlyph, TYPE_META, shortAgo } from "./inbox-list-item";

/** Hard reply limits the backend's moderation enforces (X post length; LinkedIn comment length). */
const REPLY_LIMITS: Record<string, number> = { twitter: 280, linkedin: 1250 };

const SEVERITY: Record<string, string> = {
  high: "border-red-200 bg-red-50 text-red-700",
  medium: "border-amber-300 bg-amber-50 text-amber-800",
  low: "border-slate-300 bg-slate-100 text-slate-600",
};

type SendStage = "idle" | "confirm" | "sending" | "flagged";

function sendError(err: unknown): string {
  if (err instanceof ApiError) {
    const d = err.detail as { message?: string } | undefined;
    if (d && typeof d === "object" && typeof d.message === "string") return d.message;
    if (err.status === 404) return "That message isn't in this account's inbox any more. Refresh and try again.";
    return err.message;
  }
  return "Couldn't send the reply — nothing was posted. Try again.";
}

export function InboxDetail({
  item,
  account,
  clientId,
  suggestion,
  onSuggestion,
  onToggleHandled,
  onSent,
  generationsUsed,
  generationsLimit,
  onGenerated,
  hasBrandProfile,
}: {
  item: InboxItem;
  account: InboxAccount | undefined;
  clientId: string;
  suggestion: ReplySuggestion | undefined;
  onSuggestion: (s: ReplySuggestion) => void;
  onToggleHandled: () => void;
  onSent: (replyUrl: string) => void;
  generationsUsed?: number;
  generationsLimit?: number;
  onGenerated: () => void;
  hasBrandProfile: boolean;
}) {
  const [draft, setDraft] = useState("");
  const [replyFocused, setReplyFocused] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState<string | null>(null);
  const [stage, setStage] = useState<SendStage>("idle");
  const [issues, setIssues] = useState<ModerationIssue[]>([]);
  const [sendErr, setSendErr] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  const typeMeta = TYPE_META[item.type];
  const label = platformLabel(item.platform);
  const limit = REPLY_LIMITS[item.platform] ?? 280;
  const over = draft.length > limit;
  const canSend = Boolean(account?.reply_supported && account.status === "ok" && account.account_id);
  const replied = Boolean(item.reply_url);

  const suggest = async () => {
    setGenerating(true);
    setGenError(null);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const result = await inboxApi.suggest(
        {
          client_id: clientId,
          platform: item.platform,
          type: item.type,
          author: item.author.handle || item.author.name,
          text: item.text,
        },
        controller.signal
      );
      onSuggestion(result);
      onGenerated();
      trackFeature("inbox-suggest-reply");
    } catch (err) {
      if (controller.signal.aborted) return;
      if (isGenerationQuotaError(err)) {
        setGenError("You've used this period's generations. Upgrade in Settings › Billing for more.");
      } else {
        setGenError("Couldn't generate a suggestion — try again. No generation was used.");
      }
    } finally {
      abortRef.current = null;
      setGenerating(false);
    }
  };

  const cancelSuggest = () => abortRef.current?.abort();

  const send = async (override = false) => {
    setStage("sending");
    setSendErr(null);
    try {
      const res = await inboxApi.reply({
        client_id: clientId,
        account_id: account!.account_id!,
        item_id: item.id,
        text: draft.trim(),
        override,
      });
      setStage("idle");
      setDraft("");
      onSent(res.url);
      trackFeature("inbox-reply");
      toast.success(`Reply posted to ${label}`);
    } catch (err) {
      const detail = err instanceof ApiError ? (err.detail as { code?: string; issues?: ModerationIssue[] }) : null;
      if (apiErrorStatus(err) === 409 && detail?.code === "moderation_flagged") {
        setIssues(detail.issues ?? []);
        setStage("flagged");
        return;
      }
      setStage("idle");
      setSendErr(sendError(err));
    }
  };

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(draft.trim());
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      toast.error("Couldn't copy — select the text and copy it manually.");
    }
  };

  return (
    <div className="min-w-0 rounded-[10px] border border-line bg-panel/70 p-6 shadow-soft backdrop-blur-xl motion-safe:animate-screen-in">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          {item.author.avatar ? (
            // eslint-disable-next-line @next/next/no-img-element -- platform CDN avatar, not a local asset
            <img src={item.author.avatar} alt="" className="h-8 w-8 shrink-0 rounded-lg border border-line" />
          ) : (
            <PlatformGlyph platform={item.platform} size="md" />
          )}
          <div className="min-w-0">
            <div className="truncate text-[13.5px] font-medium text-ink">{item.author.name}</div>
            <div className="truncate font-mono text-[10px] text-muted">
              {label} · {typeMeta.label}
              {item.created_at ? ` · ${shortAgo(item.created_at)} ago` : ""}
              {item.author.handle && item.author.handle !== item.author.name ? ` · ${item.author.handle}` : ""}
            </div>
          </div>
        </div>
        <button
          type="button"
          onClick={onToggleHandled}
          aria-pressed={item.handled}
          className={cn(
            "press-scale flex items-center gap-1.5 rounded-[7px] border px-3 py-1.5 text-[11.5px] font-medium",
            item.handled ? "border-emerald-300 bg-emerald-50 text-emerald-700" : "border-slate-300 text-slate-600"
          )}
        >
          <CheckCircle2 className="h-3.5 w-3.5" /> {item.handled ? "Handled" : "Mark as handled"}
        </button>
      </div>

      <div className="mt-4 rounded-lg border border-line bg-canvas/60 px-4 py-3">
        <p className="whitespace-pre-wrap break-words text-[13.5px] leading-relaxed text-slate-600">{item.text}</p>
        <div className="mt-2 flex flex-wrap gap-3 font-mono text-[10.5px] text-muted">
          <a href={item.url} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1 hover:text-ink">
            <ExternalLink className="h-3 w-3" /> Open on {label}
          </a>
          {item.in_reply_to && (
            <a
              href={item.in_reply_to.url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 hover:text-ink"
            >
              <ExternalLink className="h-3 w-3" /> {item.type === "comment" ? "On post" : "In reply to"}
            </a>
          )}
        </div>
      </div>

      {replied && (
        <p className="mt-3 flex items-center gap-1.5 font-mono text-[11px] text-emerald-600">
          <CheckCircle2 className="h-3.5 w-3.5" /> You replied from CampaignForge ·{" "}
          <a href={item.reply_url!} target="_blank" rel="noopener noreferrer" className="underline">
            view reply
          </a>
        </p>
      )}

      {/* Suggested reply */}
      <div className="mt-4">
        <div className="mb-2 flex items-center justify-between gap-2">
          <span className="text-[11.5px] font-medium text-muted">
            {suggestion?.needs_personal_attention ? "Escalation flag" : "Suggested reply"}
          </span>
          <div className="flex items-center gap-2">
            {!generating && <QuotaHint used={generationsUsed} limit={generationsLimit} noun="generations left" />}
            <button
              type="button"
              onClick={suggest}
              disabled={generating}
              className="press-scale flex items-center gap-1 text-[11px] font-medium text-accent-text disabled:opacity-70"
            >
              {generating ? (
                <>
                  <Loader2 className="h-3 w-3 animate-spin" /> Thinking…
                </>
              ) : (
                <>
                  <Sparkle className="h-3 w-3" /> {suggestion ? "Regenerate" : "Suggest a reply"}
                </>
              )}
            </button>
            {generating && (
              <button type="button" onClick={cancelSuggest} className="font-mono text-[10.5px] text-muted underline">
                Cancel
              </button>
            )}
          </div>
        </div>

        {genError && <ErrorBanner message={genError} onRetry={suggest} />}

        {suggestion ? (
          suggestion.needs_personal_attention ? (
            <div className="flex items-start gap-2 rounded-lg border border-accent/40 bg-accent/5 px-3 py-2.5 motion-safe:animate-screen-in">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent-text" />
              <div>
                <div className="text-[11.5px] font-medium text-accent-text">
                  The crew thinks this one&apos;s worth answering yourself
                </div>
                <div className="mt-1 text-[12.5px] text-slate-600">{suggestion.suggestion}</div>
              </div>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setDraft(suggestion.suggestion)}
              className="flex w-full items-start gap-2 rounded-lg border border-dashed border-accent/40 bg-accent/10 px-3 py-2.5 text-left transition-colors duration-200 hover:bg-accent/20 motion-safe:animate-screen-in"
            >
              <Sparkle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent-text" />
              <div>
                <div className="font-mono text-[9.5px] uppercase tracking-widest text-accent-text">Tap to use</div>
                <div className="mt-1 text-[12.5px] text-slate-600">{suggestion.suggestion}</div>
              </div>
            </button>
          )
        ) : (
          !generating &&
          !genError && (
            <p className="rounded-lg border border-dashed border-line px-3 py-2.5 text-xs text-muted">
              Ask the crew for a reply in {hasBrandProfile ? "this client's" : "a plain"} voice — you edit it, you
              send it. Uses one generation.
              {!hasBrandProfile && (
                <>
                  {" "}
                  <Link href="/setup/profile" className="underline">
                    Add a brand profile
                  </Link>{" "}
                  for on-voice suggestions.
                </>
              )}
            </p>
          )
        )}
      </div>

      {/* Draft + send */}
      <div className="mt-4">
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onFocus={() => setReplyFocused(true)}
          onBlur={() => setReplyFocused(false)}
          placeholder="Write your reply — you're always the one sending it…"
          rows={3}
          aria-label="Your reply"
          className={cn(
            "w-full resize-none rounded-lg border bg-canvas/60 px-3 py-2.5 text-[13px] text-ink outline-none transition-all duration-200",
            replyFocused ? "border-accent ring-[3px] ring-accent/15" : "border-line"
          )}
        />
        <div className="mt-1 flex justify-end">
          <span className={cn("font-mono text-[10.5px]", over ? "text-red-600" : "text-muted")}>
            {draft.length}/{limit}
          </span>
        </div>

        {sendErr && <ErrorBanner message={sendErr} onRetry={() => setStage("confirm")} />}

        <div className="mt-2 flex flex-wrap items-center gap-3">
          {canSend && (
            <Button onClick={() => setStage("confirm")} disabled={!draft.trim() || stage === "sending"}>
              <Send className="h-3.5 w-3.5" /> Send reply
            </Button>
          )}
          <Button variant={canSend ? "secondary" : "primary"} onClick={copy} disabled={!draft.trim()}>
            <Copy className="h-3.5 w-3.5" /> {copied ? "Copied" : "Copy reply"}
          </Button>
          {copied && !canSend && (
            <a
              href={item.url}
              target="_blank"
              rel="noopener noreferrer"
              className="font-mono text-[11px] text-ink underline motion-safe:animate-screen-in"
            >
              Open on {label} to paste it
            </a>
          )}
        </div>
        {!canSend && (
          <p className="mt-2 text-[11.5px] text-muted">
            {account?.status && account.status !== "ok"
              ? `Sending is paused while this ${label} account can't be read — copy the reply and post it on ${label}.`
              : `Replying from CampaignForge isn't available on ${label} — copy the reply and post it there.`}
          </p>
        )}
      </div>

      <PostDialog
        open={stage === "confirm" || stage === "sending"}
        onOpenChange={(o) => !o && setStage("idle")}
        busy={stage === "sending"}
        title={`Post this reply on ${label}?`}
        description={
          <>
            It posts publicly from {account?.handle || `the connected ${label} account`}, in reply to {item.author.name}.
            Moderation checks it first; nothing is posted if it flags something.
          </>
        }
        footer={
          <>
            <Button variant="secondary" onClick={() => setStage("idle")} disabled={stage === "sending"}>
              Cancel
            </Button>
            <Button onClick={() => send(false)} disabled={stage === "sending"} autoFocus>
              {stage === "sending" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
              Post reply
            </Button>
          </>
        }
      >
        <p className="whitespace-pre-wrap break-words rounded-lg border border-line bg-canvas/60 p-3 text-[13px] text-ink">
          {draft.trim()}
        </p>
      </PostDialog>

      <PostDialog
        open={stage === "flagged"}
        onOpenChange={(o) => !o && setStage("idle")}
        tone="warning"
        title={
          <span className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 shrink-0 text-amber-600" aria-hidden />
            Moderation flagged this reply
          </span>
        }
        description="Nothing was posted. Edit the reply, or send it anyway — an override is recorded in the audit log."
        footer={
          <>
            <Button variant="secondary" onClick={() => send(true)}>
              Send anyway
            </Button>
            <Button onClick={() => setStage("idle")} autoFocus>
              Go back and edit
            </Button>
          </>
        }
      >
        <ul className="space-y-2">
          {issues.map((issue, i) => (
            <li key={i} className="flex items-start gap-3 rounded-lg border border-line bg-canvas/60 p-3">
              <span
                className={cn(
                  "mt-0.5 shrink-0 rounded-full border px-2 py-0.5 font-mono text-[10px] font-medium uppercase",
                  SEVERITY[issue.severity] ?? SEVERITY.low
                )}
              >
                {issue.severity}
              </span>
              <span className="text-sm text-ink">{issue.message}</span>
            </li>
          ))}
        </ul>
      </PostDialog>
    </div>
  );
}
