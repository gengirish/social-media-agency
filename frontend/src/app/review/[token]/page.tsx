"use client";

/*
 * The page an agency's client opens from a review link. No CampaignForge account,
 * no CampaignForge branding: the client sees their agency's name and their own
 * posts, and approves each one or says what should change.
 *
 * Everything here is unauthenticated by design — the token in the URL is the whole
 * credential and the API scopes every read and write to the one client (and
 * campaign) the link was made for (backend/src/agency/services/client_review.py).
 * Moderation still runs on approve; a flagged post comes back `approval_held` and
 * the copy says the agency will check it, never why.
 */

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { format } from "date-fns";
import { CheckCircle2, Clock, MessageSquare } from "lucide-react";
import {
  api,
  apiErrorCode,
  apiErrorMessage,
  type ReviewItem,
  type ReviewPage,
} from "@/lib/api";
import { platformLabel } from "@/lib/platforms";
import { Button } from "@/components/ui/button";
import { Textarea, Input } from "@/components/ui/field";
import { LoadingState, Notice } from "@/components/ui/empty-state";
import { Tag } from "@/components/ui/tabs";

const NAME_KEY = "cf.review.name";

function readName(): string {
  try {
    return window.localStorage.getItem(NAME_KEY) ?? "";
  } catch {
    return "";
  }
}

function saveName(name: string) {
  try {
    window.localStorage.setItem(NAME_KEY, name);
  } catch {
    // A private window or blocked storage only costs retyping the name.
  }
}

function when(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : format(d, "d MMM yyyy");
}

export default function ClientReviewPage() {
  const { token } = useParams<{ token: string }>();
  const [page, setPage] = useState<ReviewPage | null>(null);
  const [failure, setFailure] = useState<{ code: string | null; message: string } | null>(null);
  const [name, setName] = useState("");

  const load = useCallback(() => {
    if (!token) return;
    setFailure(null);
    api
      .getReview(token)
      .then(setPage)
      .catch((err) =>
        setFailure({
          code: apiErrorCode(err),
          message: apiErrorMessage(err) ?? "This review page couldn't be loaded. Try again shortly.",
        })
      );
  }, [token]);

  useEffect(load, [load]);
  useEffect(() => setName(readName()), []);

  if (failure) {
    const ended = ["link_expired", "link_revoked", "link_inactive", "link_not_found"].includes(
      failure.code ?? ""
    );
    return (
      <Shell>
        <div className="mx-auto max-w-md py-24 text-center">
          <h1 className="font-display text-2xl font-semibold text-ink">
            {ended ? "This link has ended" : "Something went wrong"}
          </h1>
          <p className="mt-3 text-sm text-muted">{failure.message}</p>
          {!ended && (
            <Button className="mt-6" variant="secondary" onClick={load}>
              Try again
            </Button>
          )}
        </div>
      </Shell>
    );
  }

  if (!page) {
    return (
      <Shell>
        <LoadingState label="Loading your posts" />
      </Shell>
    );
  }

  const replace = (item: ReviewItem) =>
    setPage((prev) => {
      if (!prev) return prev;
      const pending = prev.pending.filter((p) => p.id !== item.id);
      const decided = prev.decided.filter((p) => p.id !== item.id);
      // Changes requested stays Pending on the agency's side, but for the client
      // it is decided until the agency sends a new version.
      return { ...prev, pending, decided: [item, ...decided] };
    });

  const expires = when(page.expires_at);
  // A post the client already answered stays Pending on the agency's side (changes
  // requested, or an approval moderation held), so split on the answer, not status.
  const answeredPending = (p: ReviewItem) =>
    p.client_review?.decision === "changes_requested" || p.client_review?.decision === "approval_held";
  const waiting = page.pending.filter((p) => !answeredPending(p));
  const answered = [...page.pending.filter(answeredPending), ...page.decided];

  return (
    <Shell agency={page.agency}>
      <header className="space-y-2 border-b border-line pb-6">
        <p className="font-mono text-[11px] uppercase tracking-wider text-muted">
          For review · {page.client.name}
        </p>
        <h1 className="font-display text-2xl font-semibold tracking-tight text-ink sm:text-3xl">
          {page.campaign ? page.campaign.name : `Posts for ${page.client.name}`}
        </h1>
        <p className="max-w-2xl text-sm text-muted">
          {page.agency.name} prepared these posts. Approve each one, or tell them what to change.
          Nothing is posted until it has been approved.
          {expires && <> This link works until {expires}.</>}
        </p>
      </header>

      <div className="mt-6 max-w-sm">
        <label htmlFor="reviewer-name" className="text-xs font-medium text-muted">
          Your name <span className="font-normal">(optional — shown to {page.agency.name})</span>
        </label>
        <Input
          id="reviewer-name"
          className="mt-1"
          value={name}
          maxLength={120}
          autoComplete="name"
          onChange={(e) => setName(e.target.value)}
          onBlur={() => saveName(name.trim())}
        />
      </div>

      <section className="mt-8 space-y-4" aria-labelledby="waiting-heading">
        <h2 id="waiting-heading" className="font-display text-lg font-semibold text-ink">
          Waiting for you <span className="font-mono text-sm text-muted">({waiting.length})</span>
        </h2>
        {waiting.length === 0 ? (
          <p className="rounded-xl border border-dashed border-line p-6 text-center text-sm text-muted">
            You&apos;re all caught up — nothing is waiting for your review.
          </p>
        ) : (
          waiting.map((item) => (
            <ReviewCard key={item.id} token={token} item={item} name={name} onDecided={replace} />
          ))
        )}
      </section>

      {answered.length > 0 && (
        <section className="mt-10 space-y-4" aria-labelledby="answered-heading">
          <h2 id="answered-heading" className="font-display text-lg font-semibold text-ink">
            Already reviewed
          </h2>
          {answered.map((item) => (
            <ReviewCard key={item.id} token={token} item={item} name={name} onDecided={replace} />
          ))}
        </section>
      )}
    </Shell>
  );
}

function Shell({
  agency,
  children,
}: {
  agency?: ReviewPage["agency"];
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-canvas text-ink">
      <div
        className="h-1 w-full bg-accent"
        // The agency's own colour when its white-label sets one; validated as a
        // six-digit hex by the API before it is ever sent here.
        style={agency?.primary_color ? { backgroundColor: agency.primary_color } : undefined}
        aria-hidden
      />
      <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
        {agency && (
          <div className="mb-8 flex items-center gap-3">
            {agency.logo_url && (
              // eslint-disable-next-line @next/next/no-img-element -- agency-hosted logo, not a local asset
              <img src={agency.logo_url} alt="" className="h-8 max-w-[140px] object-contain" />
            )}
            <span className="text-sm font-semibold text-ink">{agency.name}</span>
          </div>
        )}
        {children}
        {agency?.support_email && (
          <p className="mt-12 text-xs text-muted">
            Questions? <a className="underline" href={`mailto:${agency.support_email}`}>{agency.support_email}</a>
          </p>
        )}
      </div>
    </div>
  );
}

function ReviewCard({
  token,
  item,
  name,
  onDecided,
}: {
  token: string;
  item: ReviewItem;
  name: string;
  onDecided: (item: ReviewItem) => void;
}) {
  const [mode, setMode] = useState<"idle" | "changes">("idle");
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [held, setHeld] = useState(false);

  const review = item.client_review;
  const decided =
    item.status !== "pending" ||
    review?.decision === "changes_requested" ||
    review?.decision === "approval_held" ||
    held;

  async function send(decision: "approve" | "request_changes") {
    setBusy(true);
    setError(null);
    try {
      const res = await api.decideReview(token, item.id, {
        decision,
        comment: decision === "request_changes" ? comment.trim() : undefined,
        name: name.trim() || undefined,
      });
      onDecided(res.item);
      setMode("idle");
    } catch (err) {
      const code = apiErrorCode(err);
      if (code === "approval_held") {
        setHeld(true);
      } else {
        setError(apiErrorMessage(err) ?? "That didn't go through. Try again.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="rounded-xl border border-line bg-panel/70 p-5 shadow-soft">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Tag className="text-ink">{platformLabel(item.platform)}</Tag>
        <Outcome item={item} held={held} />
      </div>
      {item.title && item.content_type.endsWith("_ad") && (
        <h3 className="mt-3 text-sm font-semibold text-ink">{item.title}</h3>
      )}
      <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-ink">{item.body}</p>
      {item.hashtags.length > 0 && (
        <p className="mt-2 font-mono text-xs text-accent-text">
          {item.hashtags.map((t) => `#${t.replace(/^#/, "")}`).join(" ")}
        </p>
      )}
      {item.media_urls.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {item.media_urls.map((url) => (
            // eslint-disable-next-line @next/next/no-img-element -- storage CDN asset, not a local one
            <img key={url} src={url} alt="" className="h-28 w-28 rounded-lg border border-line object-cover" />
          ))}
        </div>
      )}
      {review?.comment && (
        <p className="mt-3 rounded-lg border border-line bg-slate-500/5 p-3 text-sm text-ink">
          <span className="font-medium">{review.name || "You"}:</span> {review.comment}
        </p>
      )}

      {held && (
        <Notice tone="info" className="mt-4">
          Thanks — your agency needs to check this post before it can be approved. They have been told.
        </Notice>
      )}
      {error && <p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}

      {!decided && mode === "idle" && (
        <div className="mt-4 flex flex-wrap gap-2">
          <Button size="sm" onClick={() => send("approve")} disabled={busy}>
            <CheckCircle2 className="h-3.5 w-3.5" /> {busy ? "Saving…" : "Approve"}
          </Button>
          <Button size="sm" variant="secondary" onClick={() => setMode("changes")} disabled={busy}>
            <MessageSquare className="h-3.5 w-3.5" /> Request changes
          </Button>
        </div>
      )}
      {!decided && mode === "changes" && (
        <div className="mt-4 space-y-2">
          <label htmlFor={`comment-${item.id}`} className="text-xs font-medium text-muted">
            What should change?
          </label>
          <Textarea
            id={`comment-${item.id}`}
            rows={3}
            maxLength={2000}
            value={comment}
            autoFocus
            onChange={(e) => setComment(e.target.value)}
          />
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              onClick={() => send("request_changes")}
              disabled={busy || comment.trim().length === 0}
            >
              {busy ? "Sending…" : "Send to agency"}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setMode("idle")} disabled={busy}>
              Cancel
            </Button>
          </div>
        </div>
      )}
    </article>
  );
}

function Outcome({ item, held }: { item: ReviewItem; held: boolean }) {
  const decision = item.client_review?.decision;
  if (held || decision === "approval_held") {
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium text-muted">
        <Clock className="h-3.5 w-3.5" aria-hidden /> With your agency
      </span>
    );
  }
  if (decision === "changes_requested" && item.status === "pending") {
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium text-amber-700">
        <MessageSquare className="h-3.5 w-3.5" aria-hidden /> Changes requested
      </span>
    );
  }
  if (item.status !== "pending") {
    const label =
      item.status === "published" ? "Approved · posted" : item.status === "scheduled" ? "Approved · scheduled" : "Approved";
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-700">
        <CheckCircle2 className="h-3.5 w-3.5" aria-hidden /> {label}
      </span>
    );
  }
  return <span className="text-xs text-muted">Waiting for you</span>;
}
