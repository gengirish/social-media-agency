"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Lightbulb, Loader2, Sparkles } from "lucide-react";
import { trackFeature } from "@/lib/analytics";
import { createKitsApi, type Prfaq, type QA } from "@/lib/api-create-kits";
import { Button } from "@/components/ui/button";
import { ErrorBanner } from "@/components/ui/feedback";
import { CancelLink, useGenerator } from "@/components/create-kits/kit-shared";
import { cn } from "@/lib/utils";

/**
 * The confirm step before a stress-test run (CF-13).
 *
 * States the cost up front, and asks for the one thing the brand profile does
 * not carry: what is actually being launched. It is optional — the run works
 * without it — but supplying it is the difference between the model reasoning
 * about a real product and filling the gap with a plausible one.
 */
function RunConfirm({
  note,
  setNote,
  onRun,
  onCancel,
  regenerate,
}: {
  note: string;
  setNote: (value: string) => void;
  onRun: () => void;
  onCancel: () => void;
  regenerate: boolean;
}) {
  return (
    <div className="mt-3 rounded-md border border-line bg-panel/70 p-3">
      <label htmlFor="prfaq-note" className="text-[12.5px] font-medium text-ink">
        What are you launching? <span className="font-normal text-muted">(optional)</span>
      </label>
      <p className="mt-1 text-[11.5px] leading-relaxed text-muted">
        A line or two about the product, who it&apos;s for and what&apos;s new. Without it the
        stress-test has only the brand profile to go on.
      </p>
      <textarea
        id="prfaq-note"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        rows={3}
        maxLength={600}
        placeholder="A scheduling tool for freelance designers — the new thing is the client-approval flow."
        className="mt-2 w-full rounded-md border border-line bg-canvas/40 px-2.5 py-2 text-[12.5px] text-ink placeholder:text-muted focus:border-accent focus:outline-none"
      />
      <p className="mt-2 flex items-center gap-1.5 text-[11.5px] text-muted">
        <AlertTriangle className="h-3 w-3 shrink-0 text-amber-600" aria-hidden />
        Uses 1 generation and takes about a minute.
        {regenerate && " This replaces the current stress-test."}
      </p>
      <div className="mt-2.5 flex items-center gap-2">
        <Button size="sm" onClick={onRun}>
          <Sparkles className="h-3 w-3" /> {regenerate ? "Regenerate" : "Run stress-test"}
        </Button>
        <button
          type="button"
          onClick={onCancel}
          className="font-mono text-[11px] text-muted underline hover:text-ink"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

function FaqList({ items }: { items: QA[] }) {
  return (
    <div className="mb-3 mt-1 space-y-2">
      {items.map((qa, i) => (
        <div key={i}>
          <div className="text-[12.5px] font-semibold text-ink">{qa.question}</div>
          <div className="text-xs text-slate-600">{qa.answer}</div>
        </div>
      ))}
    </div>
  );
}

/**
 * Cadence's PRFAQ stress-test box on the Product-launch mode: Amazon's
 * "Working Backwards" press release + FAQs + the single weakest claim. One per
 * client, replaced on regenerate; the launch-kit generator reads it. It judges
 * positioning on its own — the campaign focus is deliberately not an input.
 */
export function PrfaqPanel({
  clientId,
  disabled,
  onCharged,
}: {
  clientId: string;
  /** No brand profile or no generations left — the parent shows why. */
  disabled: boolean;
  /** A stress-test run spends a generation; the parent refreshes its quota. */
  onCharged: () => void;
}) {
  const [prfaq, setPrfaq] = useState<Prfaq | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [expanded, setExpanded] = useState(false);
  /*
   * CF-13: one click used to start a ~60-second run and spend a generation with
   * no warning, no input and no progress. The button now opens a confirm step
   * that states the cost and takes an optional note about what is being
   * launched — which the brand profile alone does not say, and which is why the
   * model was left to fill that gap itself.
   */
  const [confirming, setConfirming] = useState(false);
  const [note, setNote] = useState("");
  const gen = useGenerator(clientId);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await createKitsApi.getPrfaq(clientId);
      setPrfaq(res.prfaq);
      setLoadError(false);
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, [clientId]);

  useEffect(() => {
    setExpanded(false);
    void load();
  }, [load]);

  const run = useCallback(async () => {
    setConfirming(false);
    const res = await gen.run((signal) => createKitsApi.runPrfaq(clientId, note, signal));
    if (res) {
      setPrfaq(res.prfaq);
      setExpanded(true);
      trackFeature("prfaq-stress-test", { with_note: note.trim().length > 0 });
    }
    onCharged();
  }, [gen, clientId, note, onCharged]);

  const failed = gen.failure === "error";
  const retryMessage = prfaq
    ? "Couldn't regenerate the stress-test — no quota was used. Try again."
    : "Couldn't run the stress-test — no quota was used. Try again.";

  if (loading) {
    return (
      <div className="mb-5 flex items-center gap-2 rounded-lg border border-line p-4 font-mono text-[11px] text-muted">
        <Loader2 className="h-3 w-3 animate-spin" /> Checking for a stress-test…
      </div>
    );
  }
  if (loadError) {
    return (
      <div className="mb-5">
        <ErrorBanner message="Couldn't load the PRFAQ stress-test." onRetry={() => void load()} />
      </div>
    );
  }

  return (
    <div
      className={cn(
        "mb-5 rounded-lg border p-4 motion-safe:animate-screen-in",
        prfaq ? "border-sky-300 bg-sky-50/60" : "border-line bg-slate-500/[0.03]"
      )}
    >
      {!prfaq ? (
        <>
          <div className="flex items-center gap-1.5 text-[11.5px] font-medium text-muted">
            <Lightbulb className="h-3 w-3" /> Recommended before generating copy
          </div>
          <p className="mb-3 mt-2 max-w-[560px] text-xs leading-relaxed text-muted">
            Amazon&apos;s &ldquo;Working Backwards&rdquo; method: write the press release as if this already launched, before
            writing any actual launch copy. If it doesn&apos;t read as compelling yet, that&apos;s real signal worth knowing
            before the tagline gets written, not after.
          </p>
          <div className="flex items-center gap-3">
            <Button
              size="sm"
              variant="secondary"
              onClick={() => setConfirming(true)}
              disabled={gen.generating || disabled || confirming}
            >
              {gen.generating ? (
                <>
                  <Loader2 className="h-3 w-3 animate-spin" /> Stress-testing…
                </>
              ) : (
                <>
                  <Sparkles className="h-3 w-3" /> Run PRFAQ stress-test
                </>
              )}
            </Button>
            {gen.generating && <CancelLink onClick={gen.cancel} />}
          </div>
          {gen.generating && (
            <p className="mt-2 text-[11.5px] text-muted">
              Writing the press release, both FAQs and the critique — about a minute.
            </p>
          )}
          {confirming && !gen.generating && (
            <RunConfirm
              note={note}
              setNote={setNote}
              onRun={() => void run()}
              onCancel={() => setConfirming(false)}
              regenerate={false}
            />
          )}
        </>
      ) : (
        <>
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-1.5 text-[11.5px] font-medium text-sky-700">
              <CheckCircle2 className="h-3 w-3 animate-pop-in" /> PRFAQ stress-test complete — feeding into launch kit
              generation
            </div>
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              aria-expanded={expanded}
              className="shrink-0 text-[11.5px] font-medium text-muted underline hover:text-ink"
            >
              {expanded ? "Collapse" : "View"}
            </button>
          </div>
          {expanded && (
            <div className="mt-3 motion-safe:animate-screen-in">
              <div className="text-[11px] font-medium text-muted">Mock press release</div>
              <p className="mb-3 mt-1 text-[13px] font-semibold text-ink">{prfaq.press_release_headline}</p>
              <p className="mb-3 whitespace-pre-wrap text-[12.5px] leading-relaxed text-slate-600">
                {prfaq.press_release_body}
              </p>
              <div className="text-[11px] font-medium text-muted">Customer FAQ</div>
              <FaqList items={prfaq.customer_faq} />
              <div className="text-[11px] font-medium text-muted">Internal FAQ — the tough questions</div>
              <FaqList items={prfaq.internal_faq} />
              <div className="rounded-md border border-accent/30 bg-accent/5 p-3">
                <div className="text-[11px] font-medium text-accent-text">Weakest claim, honestly</div>
                <p className="mt-1 text-[12.5px] leading-normal text-slate-600">{prfaq.weakest_claim}</p>
                <div className="mt-2 text-[11px] font-medium text-accent-text">A sharper version would say</div>
                <p className="mt-1 text-[12.5px] leading-normal text-slate-600">{prfaq.sharper_version_note}</p>
              </div>
            </div>
          )}
          <div className="mt-3 flex items-center gap-3">
            <Button
              size="sm"
              variant="secondary"
              onClick={() => setConfirming(true)}
              disabled={gen.generating || disabled || confirming}
            >
              {gen.generating ? (
                <>
                  <Loader2 className="h-3 w-3 animate-spin" /> Regenerating…
                </>
              ) : (
                "Regenerate stress-test"
              )}
            </Button>
            {gen.generating && <CancelLink onClick={gen.cancel} />}
          </div>
          {gen.generating && (
            <p className="mt-2 text-[11.5px] text-muted">
              Writing the press release, both FAQs and the critique — about a minute.
            </p>
          )}
          {confirming && !gen.generating && (
            <RunConfirm
              note={note}
              setNote={setNote}
              onRun={() => void run()}
              onCancel={() => setConfirming(false)}
              regenerate
            />
          )}
        </>
      )}
      {failed && <ErrorBanner message={gen.message ?? retryMessage} onRetry={() => void run()} />}
    </div>
  );
}
