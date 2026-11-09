"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { Lightbulb, Loader2, RefreshCw, Wand2 } from "lucide-react";
import {
  api,
  apiErrorCode,
  apiErrorMessage,
  apiErrorStatus,
  type CampaignSuggestion,
} from "@/lib/api";
import { trackFeature } from "@/lib/analytics";
import { platformLabel } from "@/lib/platforms";
import { Button } from "@/components/ui/button";
import { ErrorBanner } from "@/components/ui/feedback";
import { Field, Input } from "@/components/ui/field";

const ANGLE_LABELS: Record<string, string> = {
  launch_offer: "Launch or offer",
  thought_leadership: "Thought leadership",
  community: "Community",
  timely: "Timely moment",
};

const HINT_MAX = 500;

export function angleLabel(angle: string): string {
  return ANGLE_LABELS[angle] ?? angle.replace(/_/g, " ");
}

/** A yyyy-mm-dd string as DD/MM/YYYY (house convention), or the raw value if it is not one. */
function formatDate(raw: string): string {
  const [y, m, d] = (raw ?? "").split("-");
  return y && m && d ? `${d}/${m}/${y}` : raw;
}

type Failure =
  | { kind: "profile" }
  | { kind: "quota"; message: string | null }
  | { kind: "other"; message: string };

/**
 * "Suggest campaigns" on New Campaign's Brief step.
 *
 * Asks the model for 2–3 different campaigns for the chosen client. Nothing is
 * created: "Use this" hands one to the wizard, which copies it into the form for
 * the user to edit and launch. Following the shared generator rule for anything
 * that is not Post Studio, Cancel only stops the browser waiting — a request the
 * server finishes still uses a generation, and the copy says so.
 */
export function CampaignSuggestions({
  clientId,
  startDate,
  endDate,
  hasEdits,
  onUse,
}: {
  clientId: string;
  /** The form's dates, sent only when the user has already set them. */
  startDate: string;
  endDate: string;
  /** True when the form holds values a pick would overwrite — ask first. */
  hasEdits: boolean;
  onUse: (suggestion: CampaignSuggestion) => void;
}) {
  const [hint, setHint] = useState("");
  const [loading, setLoading] = useState(false);
  const [suggestions, setSuggestions] = useState<CampaignSuggestion[]>([]);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [confirming, setConfirming] = useState<number | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  // Suggestions belong to the client they were written for; switching client
  // drops them (and abandons any request still in flight).
  useEffect(() => {
    controllerRef.current?.abort();
    controllerRef.current = null;
    setLoading(false);
    setSuggestions([]);
    setFailure(null);
    setConfirming(null);
  }, [clientId]);

  useEffect(() => () => controllerRef.current?.abort(), []);

  async function suggest() {
    if (!clientId || loading) return;
    const controller = new AbortController();
    controllerRef.current = controller;
    setLoading(true);
    setFailure(null);
    setConfirming(null);
    const trimmedHint = hint.trim().slice(0, HINT_MAX);
    try {
      const res = await api.suggestCampaigns(
        {
          client_id: clientId,
          ...(startDate ? { start_date: startDate } : {}),
          ...(endDate ? { end_date: endDate } : {}),
          ...(trimmedHint ? { hint: trimmedHint } : {}),
        },
        controller.signal
      );
      if (controller.signal.aborted) return;
      const items = Array.isArray(res.suggestions) ? res.suggestions : [];
      setSuggestions(items);
      if (items.length) trackFeature("campaign-suggestions");
      else setFailure({ kind: "other", message: "Couldn't come up with usable suggestions. Try again." });
    } catch (err) {
      if (controller.signal.aborted) return;
      const status = apiErrorStatus(err);
      if (apiErrorCode(err) === "brand_profile_required") {
        setFailure({ kind: "profile" });
      } else if (status === 402 || apiErrorCode(err) === "generation_quota_exceeded") {
        setFailure({ kind: "quota", message: apiErrorMessage(err) });
      } else if (status === 404) {
        setFailure({ kind: "other", message: "That client no longer exists in this workspace." });
      } else if (status === 422) {
        setFailure({
          kind: "other",
          message:
            "Those dates don't work for a suggestion — check the start and end dates on the Channels step, or clear them.",
        });
      } else if (status === 502) {
        setFailure({
          kind: "other",
          message: "Couldn't come up with usable suggestions — no generation was used. Try again.",
        });
      } else {
        setFailure({
          kind: "other",
          message: err instanceof Error && err.message ? err.message : "Couldn't get suggestions right now. Try again.",
        });
      }
    } finally {
      if (controllerRef.current === controller) {
        controllerRef.current = null;
        setLoading(false);
      }
    }
  }

  function cancel() {
    controllerRef.current?.abort();
    controllerRef.current = null;
    setLoading(false);
    toast("Stopped waiting. If the server had already finished, that set may still have used a generation.");
  }

  function use(index: number, confirmed = false) {
    const s = suggestions[index];
    if (!s) return;
    if (hasEdits && !confirmed) {
      setConfirming(index);
      return;
    }
    setConfirming(null);
    onUse(s);
    trackFeature("campaign-suggestion-used", { angle: s.angle });
  }

  const hasResults = suggestions.length > 0;

  return (
    <section
      aria-label="Campaign suggestions"
      className="space-y-3 rounded-lg border border-line bg-canvas/40 p-4"
      data-testid="campaign-suggestions"
    >
      <div className="flex items-start gap-2">
        <Lightbulb aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-accent-text" />
        <div className="space-y-0.5">
          <p className="text-sm font-medium text-ink">Not sure what to run?</p>
          <p className="text-xs text-muted">
            Get 2–3 different campaign ideas written from this client&apos;s brand profile. Pick one to fill the
            brief, then edit it as you like. Uses 1 generation; nothing is created until you press Launch.
          </p>
        </div>
      </div>

      <Field label="Anything on your mind? (optional)" htmlFor="campaign-suggest-hint">
        <Input
          id="campaign-suggest-hint"
          autoComplete="off"
          value={hint}
          maxLength={HINT_MAX}
          onChange={(e) => setHint(e.target.value)}
          placeholder="e.g. launching v2 in December"
          disabled={loading}
        />
      </Field>

      <div className="flex flex-wrap items-center gap-3">
        <Button
          size="sm"
          variant={hasResults ? "secondary" : "primary"}
          onClick={suggest}
          disabled={!clientId || loading}
        >
          {loading ? (
            <>
              <Loader2 aria-hidden className="h-[13px] w-[13px] animate-spin" /> Thinking…
            </>
          ) : hasResults ? (
            <>
              <RefreshCw aria-hidden className="h-[13px] w-[13px]" /> Regenerate
            </>
          ) : (
            <>
              <Wand2 aria-hidden className="h-[13px] w-[13px]" /> Suggest campaigns
            </>
          )}
        </Button>
        {loading && (
          <button type="button" onClick={cancel} className="font-mono text-[11px] text-muted underline">
            Cancel
          </button>
        )}
        {!clientId && <span className="text-xs text-muted">Pick a client first.</span>}
        {hasResults && !loading && <span className="text-xs text-muted">Regenerate uses another generation.</span>}
      </div>
      {loading && (
        <p className="text-xs text-muted" aria-live="polite">
          Cancel only stops waiting here — if the server still finishes, the set uses a generation.
        </p>
      )}

      {failure?.kind === "profile" && (
        <ErrorBanner
          message={
            <>
              This client has no brand profile yet, so there is nothing to base suggestions on.{" "}
              <Link href="/setup/profile" className="text-ink underline">
                Set up the brand profile
              </Link>
            </>
          }
        />
      )}
      {failure?.kind === "quota" && (
        <ErrorBanner
          message={
            <>
              {failure.message ?? "You've used all your generations for this period."}{" "}
              <Link href="/pricing" className="text-ink underline">
                See plans in Billing
              </Link>
            </>
          }
        />
      )}
      {failure?.kind === "other" && <ErrorBanner message={failure.message} onRetry={suggest} />}

      {hasResults && (
        <ul className="grid gap-3" aria-label="Suggested campaigns">
          {suggestions.map((s, i) => {
            const channels = Array.isArray(s.channels) ? s.channels : [];
            const messages = Array.isArray(s.key_messages) ? s.key_messages : [];
            return (
              <li
                key={`${s.angle}-${i}`}
                data-testid="campaign-suggestion"
                className="space-y-2.5 rounded-lg border border-line bg-panel p-4"
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="space-y-1">
                    <span className="inline-block rounded-full border border-accent/40 bg-accent/10 px-2 py-0.5 font-mono text-[10px] font-medium text-accent-text">
                      {angleLabel(s.angle)}
                    </span>
                    <h3 className="font-display text-base font-semibold text-ink">{s.campaign_name}</h3>
                  </div>
                  <Button size="sm" onClick={() => use(i)} aria-label={`Use this: ${s.campaign_name}`}>
                    Use this
                  </Button>
                </div>
                <p className="text-sm text-ink">{s.objective}</p>
                <dl className="grid gap-1.5 text-xs sm:grid-cols-[auto_1fr] sm:gap-x-3">
                  {s.target_audience && (
                    <>
                      <dt className="text-muted">Audience</dt>
                      <dd className="text-ink">{s.target_audience}</dd>
                    </>
                  )}
                  {channels.length > 0 && (
                    <>
                      <dt className="text-muted">Channels</dt>
                      <dd className="text-ink">{channels.map(platformLabel).join(", ")}</dd>
                    </>
                  )}
                  {(s.start_date || s.end_date) && (
                    <>
                      <dt className="text-muted">Dates</dt>
                      <dd className="font-mono text-ink">
                        {formatDate(s.start_date)} – {formatDate(s.end_date)}
                      </dd>
                    </>
                  )}
                  {messages.length > 0 && (
                    <>
                      <dt className="text-muted">Key messages</dt>
                      <dd className="text-ink">
                        <ul className="list-disc space-y-0.5 pl-4">
                          {messages.map((m, j) => (
                            <li key={j}>{m}</li>
                          ))}
                        </ul>
                      </dd>
                    </>
                  )}
                </dl>
                {s.rationale && (
                  <p className="border-l-2 border-accent/50 pl-3 text-xs text-muted">
                    <span className="font-medium text-ink">Why this one: </span>
                    {s.rationale}
                  </p>
                )}
                {confirming === i && (
                  <div
                    role="alert"
                    className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2"
                  >
                    <span className="text-xs text-amber-800">
                      This replaces what&apos;s already in the brief (name, objective, audience, key messages, channels,
                      dates, additional context). Budget and paid ads stay as they are.
                    </span>
                    <span className="flex gap-2">
                      <Button size="sm" variant="secondary" onClick={() => setConfirming(null)}>
                        Keep mine
                      </Button>
                      <Button size="sm" onClick={() => use(i, true)}>
                        Replace
                      </Button>
                    </span>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
