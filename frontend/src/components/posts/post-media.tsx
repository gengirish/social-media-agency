"use client";

import { useState } from "react";
import { AlertTriangle, Download, Image as ImageIcon, Loader2, Video } from "lucide-react";
import { toast } from "sonner";
import {
  api,
  mediaErrorReason,
  type ContentPiece,
  type GeneratedImageResponse,
  type MediaAsset,
} from "@/lib/api";
import { trackFeature } from "@/lib/analytics";
import { Button, buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * Media on a post card: the thumbnail strip, the live "Create image" action, and
 * the manual-channel Download.
 *
 * Product rule 1 runs through all of it. The product generates the image and
 * stores it; on a manual channel a **human** downloads it and attaches it in the
 * composer, and nothing here may read as though the product attached or posted
 * anything. (Media does not reach a connected-channel publisher yet either —
 * that is Phase 6 — which is why the strip stays descriptive rather than
 * promising the image will go out.)
 */

/**
 * The asset records for a piece, with `media_urls` entries that have no record
 * behind them synthesised.
 *
 * `media_urls` is the denormalised projection of `media` and is what the
 * publishers read, so the two can legitimately disagree for a row written before
 * `media_asset` existed: a URL with no record. Those render, because the image is
 * real, and they carry an empty moderation status — which is honest, and is
 * exactly what the approve gate refuses with `media_unscreened`.
 */
export function mediaAssetsOf(piece: Pick<ContentPiece, "media" | "media_urls">): MediaAsset[] {
  const records = piece.media ?? [];
  const known = new Set(records.map((m) => m.url));
  const orphans: MediaAsset[] = (piece.media_urls ?? [])
    .filter((url) => url && !known.has(url))
    .map((url) => ({
      id: url,
      kind: "image",
      url,
      thumb_url: "",
      width: null,
      height: null,
      duration_ms: null,
      moderation: { status: "", reason: "", issues: [] },
    }));
  return [...records, ...orphans];
}

/**
 * Merge the server's assets with ones generated on this card since the last load.
 *
 * Newest first, matching the order `media` arrives in, so a freshly generated
 * image does not move when the list next reloads.
 */
export function withLocalMedia(
  piece: Pick<ContentPiece, "media" | "media_urls">,
  local: MediaAsset[]
): MediaAsset[] {
  const assets = mediaAssetsOf(piece);
  const seen = new Set(assets.map((a) => a.id));
  const fresh = local.filter((a) => !seen.has(a.id));
  return [...[...fresh].reverse(), ...assets];
}

/** A filename the operator can find again on their disk. */
function downloadName(asset: MediaAsset, index: number): string {
  const ext = asset.url.split("?")[0].split(".").pop();
  const safeExt = ext && /^[a-z0-9]{2,5}$/i.test(ext) ? ext : asset.kind === "video" ? "mp4" : "png";
  return `campaignforge-${asset.kind}-${index + 1}.${safeExt}`;
}

function seconds(ms: number | null): string | null {
  if (!ms || ms <= 0) return null;
  return `${Math.round(ms / 1000)}s`;
}

/**
 * Which verdicts are worth a reviewer's attention, and which are just normal.
 *
 * `provider_only` is the healthy case for most images — rung 1 of the ladder ran,
 * was clean, and no vision call was needed — so it renders as nothing at all. A
 * badge there would have cried wolf on nearly every asset and taught people to
 * ignore the one that matters. Only `flagged` and a never-screened asset get a
 * panel; a check that errored or timed out gets one quiet line, because fail-open
 * has to be visible without being alarming.
 */
type Verdict = "ok" | "flagged" | "unscreened" | "check-failed";

export function verdictOf(asset: MediaAsset): Verdict {
  // `{}` — not `{status: "", …}` — is how a never-screened asset arrives, so
  // every field here is read with a fallback.
  const { status = "", reason = "" } = asset.moderation ?? {};
  if (status === "flagged") return "flagged";
  // Healthy whichever side of the §1E correction the backend landed on: a clean
  // provider signal is a real screen, whatever status accompanies the reason.
  if (reason === "provider_only" || status === "passed") return "ok";
  if (status === "unavailable") return "check-failed";
  return "unscreened";
}

const CHECK_FAILED_COPY: Record<string, string> = {
  video_unsupported: "Videos aren't screened automatically yet — watch it before you approve it.",
  timeout: "The image check timed out, so nobody screened this — look at it before you approve it.",
  llm_error: "The image check couldn't run, so nobody screened this — look at it before you approve it.",
  unparseable_response:
    "The image check returned something unreadable, so nobody screened this — look at it before you approve it.",
};

export function PostMediaStrip({
  assets,
  manual,
}: {
  assets: MediaAsset[];
  /** This post's channel is one a human posts by hand, so the image is downloaded, not sent. */
  manual: boolean;
}) {
  if (assets.length === 0) return null;
  const flagged = assets.filter((a) => verdictOf(a) === "flagged");
  const unscreened = assets.filter((a) => verdictOf(a) === "unscreened");
  const checkFailed = assets.filter((a) => verdictOf(a) === "check-failed");

  return (
    <div className="mt-3">
      <ul className="flex flex-wrap gap-2">
        {assets.map((asset, i) => {
          const src = asset.thumb_url || asset.url;
          const duration = seconds(asset.duration_ms);
          const bad = verdictOf(asset) === "flagged";
          return (
            <li key={asset.id} className="relative">
              {/*
                A real anchor, not a click handler: the browser does the download
                inside the user's own gesture, so there is no await to lose it to
                and nothing to be popup-blocked. `download` is advisory on a
                cross-origin asset — if the CDN does not honour it the file opens
                in a new tab, where it can still be saved. Never a clipboard write:
                image-to-clipboard fails silently on too many browsers and a silent
                failure looks like we lost the asset.
              */}
              <a
                href={asset.url}
                download={downloadName(asset, i)}
                target="_blank"
                rel="noopener noreferrer"
                title={manual ? "Download this image to attach it yourself" : "Open the full-size file"}
                className={cn(
                  "block overflow-hidden rounded-md border bg-canvas transition-colors hover:border-accent",
                  bad ? "border-red-300" : "border-line"
                )}
              >
                {/* eslint-disable-next-line @next/next/no-img-element -- storage CDN asset, not a local one */}
                <img
                  src={src}
                  alt={asset.kind === "video" ? "Generated video still" : "Generated image for this post"}
                  width={96}
                  height={96}
                  loading="lazy"
                  decoding="async"
                  className="h-20 w-20 object-cover sm:h-24 sm:w-24"
                />
              </a>
              {(asset.kind === "video" || duration) && (
                <span className="pointer-events-none absolute bottom-1 left-1 inline-flex items-center gap-1 rounded bg-canvas/85 px-1 py-px font-mono text-[9.5px] text-ink">
                  <Video className="h-2.5 w-2.5" aria-hidden />
                  {duration ?? "video"}
                </span>
              )}
            </li>
          );
        })}
      </ul>

      {manual && (
        <p className="mt-1.5 text-[11px] leading-snug text-muted">
          Download the image, then attach it in the composer. CampaignForge doesn&apos;t attach it or post it for you.
        </p>
      )}

      {flagged.length > 0 && (
        <div className="mt-2 rounded-lg border border-red-200 bg-red-50 p-2.5 text-[11.5px] leading-snug text-red-700">
          <p className="flex items-start gap-1.5 font-medium">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
            {flagged.length === 1 ? "This image was flagged" : `${flagged.length} images were flagged`} — review it
            before approving the post.
          </p>
          <ul className="mt-1 ml-[1.375rem] list-disc space-y-0.5">
            {flagged.flatMap((asset) =>
              (asset.moderation.issues ?? []).map((issue, i) => (
                <li key={`${asset.id}-${i}`}>
                  {issue.message}
                  {issue.severity ? ` (${issue.severity})` : ""}
                </li>
              ))
            )}
          </ul>
        </div>
      )}

      {unscreened.length > 0 && (
        <p className="mt-2 flex items-start gap-1.5 rounded-md border border-amber-300/60 bg-amber-50/60 px-2.5 py-2 text-[11px] leading-snug text-amber-900">
          <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-amber-600" aria-hidden />
          <span>
            {unscreened.length === 1 ? "This image hasn't been screened" : "Some of these images haven't been screened"}
            . Approval checks attached media first, so it will ask for a screen before this post can go anywhere.
          </span>
        </p>
      )}

      {checkFailed.length > 0 && (
        <p className="mt-2 flex items-start gap-1.5 text-[11px] leading-snug text-muted">
          <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
          <span>
            {CHECK_FAILED_COPY[checkFailed[0].moderation?.reason ?? ""] ??
              "The automatic check didn't run on this — look at it before you approve it."}
          </span>
        </p>
      )}
    </div>
  );
}

/**
 * Generate an image for this post.
 *
 * Deliberately beside "Get creative brief" rather than instead of it: per §1F the
 * brief *is* the prompt this reads from, so hiding it would hide the input to the
 * button next to it — and an operator using a human designer still wants the words.
 *
 * No capability gate, matching Regenerate and Get creative brief on the same row:
 * the server is the gate, and the capability it will settle on is not pinned down
 * yet. Busy state is local, not the card's `busy` prop — the Queue page owns that
 * union and this stage does not touch the page.
 */
export function CreateImageButton({
  post,
  disabled,
  onCreated,
}: {
  post: Pick<ContentPiece, "id" | "platform" | "status">;
  disabled: boolean;
  onCreated: (asset: MediaAsset) => void;
}) {
  const [busy, setBusy] = useState(false);
  // An image on an already-approved piece is an unreviewed image on a post a human
  // signed off without it, so the server sends the piece back to `draft`. The card
  // cannot know that from its own copy of the row, so the toast says it outright
  // rather than leaving the badge looking authoritative.
  const resets = post.status === "approved" || post.status === "scheduled";

  async function create() {
    if (busy) return;
    setBusy(true);
    try {
      const asset: GeneratedImageResponse = await api.generateImage(post.id);
      onCreated(asset);
      trackFeature("create-image", { platform: post.platform, deduped: asset.deduped });
      const made = asset.deduped
        ? "Reused the image already generated for this prompt — no media credits used."
        : "Image created and attached to this post in CampaignForge. Nothing has been posted.";
      toast.success(
        resets ? `${made} This post is back in Pending so the image gets checked — reload to see it.` : made
      );
    } catch (err) {
      const reason = mediaErrorReason(err);
      if (reason) toast.error(reason.message);
      else toast.error(err instanceof Error ? err.message : "Couldn't make the image — try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Button variant="secondary" size="sm" onClick={() => void create()} disabled={disabled || busy}>
      {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ImageIcon className="h-3.5 w-3.5" aria-hidden />}
      {busy ? "Creating…" : "Create image"}
    </Button>
  );
}

/**
 * Download the post's media, for a channel a human posts by hand.
 *
 * §1A: this is the whole of what visual posting needs on a manual channel — no
 * media upload API, no Meta app review. An anchor rather than a button so the
 * download happens in the gesture, before any await, the same rule the composer
 * deep link follows.
 */
export function DownloadMediaAction({
  assets,
  disabled,
}: {
  assets: MediaAsset[];
  disabled: boolean;
}) {
  if (assets.length === 0) return null;
  // One anchor per asset, never one that says "download 2 files" and fetches one:
  // a browser download is one file per gesture, and a label that over-promises is
  // the same class of lie as a publish button on a channel with no tokens.
  return (
    <>
      {assets.map((asset, i) => {
        const label =
          (asset.kind === "video" ? "Download video" : "Download image") +
          (assets.length > 1 ? ` ${i + 1}` : "");
        if (disabled) {
          return (
            <span
              key={asset.id}
              className={cn(buttonVariants({ variant: "secondary", size: "sm" }), "opacity-50")}
              aria-disabled
            >
              <Download className="h-3.5 w-3.5" aria-hidden />
              {label}
            </span>
          );
        }
        return (
          <a
            key={asset.id}
            href={asset.url}
            download={downloadName(asset, i)}
            target="_blank"
            rel="noopener noreferrer"
            title="Download it, then attach it in the composer yourself"
            className={buttonVariants({ variant: "secondary", size: "sm" })}
            onClick={() => trackFeature("manual-media-download", { kind: asset.kind })}
          >
            <Download className="h-3.5 w-3.5" aria-hidden />
            {label}
          </a>
        );
      })}
    </>
  );
}
