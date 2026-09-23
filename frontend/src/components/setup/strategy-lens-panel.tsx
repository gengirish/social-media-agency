"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { CheckCircle2, Lightbulb, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ErrorBanner } from "@/components/ui/feedback";
import { Eyebrow } from "@/components/ui/panel";
import { QuotaHint } from "@/components/ui/quota-hint";
import { trackFeature } from "@/lib/analytics";
import { foundationApi, type CreativeAsset } from "@/lib/api-foundation";
import { setupApi, type StrategyLensPayload } from "@/lib/api-setup";
import { generationErrorMessage } from "./use-generation-quota";

function isPanel(p: unknown): p is StrategyLensPayload {
  const v = p as StrategyLensPayload | null;
  return !!v && Array.isArray(v.lenses) && typeof v.tension === "string" && typeof v.synthesis === "string";
}

/**
 * Cadence's StrategyLensPanel: four named frameworks applied independently,
 * then where they disagree and the one next step. Read-only analysis — it
 * changes no other agent's prompt. Each run is a `strategy_lens` creative
 * asset; this shows the latest.
 */
export function StrategyLensPanel({
  clientId,
  quota,
}: {
  clientId: string;
  quota: { used: number | null; limit: number | null; reload: () => void };
}) {
  const [panel, setPanel] = useState<CreativeAsset<StrategyLensPayload> | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(false);
    try {
      const { items } = await foundationApi.listAssets<StrategyLensPayload>({
        clientId,
        kinds: ["strategy_lens"],
        limit: 1,
      });
      setPanel(items[0] && isPanel(items[0].payload) ? items[0] : null);
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, [clientId]);

  useEffect(() => {
    void load();
    return () => abortRef.current?.abort();
  }, [load]);

  const generate = async () => {
    const controller = new AbortController();
    abortRef.current = controller;
    setGenerating(true);
    setGenError(null);
    try {
      const asset = await setupApi.runStrategyLens(clientId, controller.signal);
      setPanel(asset);
      setExpanded(true);
      trackFeature("strategy-lens");
    } catch (e) {
      if (!controller.signal.aborted) setGenError(generationErrorMessage(e, "Couldn't run the strategy lens panel — try again."));
    } finally {
      abortRef.current = null;
      setGenerating(false);
      quota.reload();
    }
  };
  const cancel = () => abortRef.current?.abort();

  if (loading) {
    return (
      <div className="flex items-center gap-2 font-mono text-[11px] text-muted">
        <Loader2 className="h-3 w-3 animate-spin" /> Loading the strategy lens panel…
      </div>
    );
  }
  if (loadError) return <ErrorBanner message="Couldn't load the strategy lens panel." onRetry={() => void load()} />;

  if (!panel) {
    return (
      <div>
        <Eyebrow>Strategy lens panel (optional)</Eyebrow>
        <p className="mb-3 mt-2 max-w-[560px] text-xs leading-relaxed text-muted">
          Runs this client&apos;s positioning through four well-established, named marketing frameworks independently —
          Jobs-to-be-Done, Category Design, Blue Ocean Strategy&apos;s ERRC grid, and Distinctive Assets — then surfaces
          where they genuinely disagree. This is framework-based analysis (real, citable methodologies), not simulated
          opinions from any person.
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <Button size="sm" onClick={() => void generate()} disabled={generating}>
            {generating ? (
              <>
                <Loader2 className="h-3 w-3 animate-spin" /> Running panel…
              </>
            ) : (
              <>
                <Lightbulb className="h-3 w-3" /> Run strategy lens panel
              </>
            )}
          </Button>
          {generating && (
            <button type="button" onClick={cancel} className="font-mono text-[11px] text-muted underline">
              Cancel
            </button>
          )}
          <QuotaHint used={quota.used} limit={quota.limit} />
        </div>
        {genError && <ErrorBanner message={genError} onRetry={() => void generate()} />}
      </div>
    );
  }

  const data = panel.payload;
  const ranAt = panel.created_at ? new Date(panel.created_at).toLocaleDateString() : null;

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Eyebrow>Strategy lens panel</Eyebrow>
          <CheckCircle2 className="h-3 w-3 text-accent-text" aria-hidden />
          {ranAt && <span className="font-mono text-[10px] text-muted">run {ranAt}</span>}
        </div>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            aria-expanded={expanded}
            className="font-mono text-[11px] text-muted underline"
          >
            {expanded ? "Collapse" : "View"}
          </button>
          <button
            type="button"
            onClick={() => void generate()}
            disabled={generating}
            className="font-mono text-[11px] text-muted underline disabled:opacity-60"
          >
            {generating ? "Regenerating…" : "Regenerate"}
          </button>
          {generating && (
            <button type="button" onClick={cancel} className="font-mono text-[11px] text-muted underline">
              Cancel
            </button>
          )}
          <QuotaHint used={quota.used} limit={quota.limit} />
        </div>
      </div>

      {expanded && (
        <div className="mt-3 motion-safe:animate-screen-in">
          <div className="space-y-3">
            {data.lenses.map((lens, i) => (
              <div
                key={`${lens.framework}-${i}`}
                style={{ animationDelay: `${i * 0.06}s` }}
                className="rounded-md border border-line bg-slate-500/5 p-3 motion-safe:animate-screen-in"
              >
                <div className="flex flex-wrap items-baseline gap-2">
                  <span className="text-[12.5px] font-semibold text-ink">{lens.framework}</span>
                  <span className="font-mono text-[10px] text-muted">— {lens.origin}</span>
                </div>
                <p className="mt-1.5 text-xs leading-normal text-slate-600">{lens.critique}</p>
                <p className="mt-1.5 text-xs leading-normal text-accent-text">
                  <strong>Suggestion:</strong> {lens.suggestion}
                </p>
              </div>
            ))}
          </div>
          <div className="mt-3 rounded-md border border-red-300/60 bg-red-50/60 p-3">
            <div className="font-mono text-[9.5px] uppercase tracking-[0.06em] text-red-600">Where these genuinely disagree</div>
            <p className="mt-1 text-[12.5px] leading-normal text-slate-600">{data.tension}</p>
          </div>
          <div className="mt-3 rounded-md border border-emerald-300/60 bg-emerald-50/60 p-3">
            <div className="font-mono text-[9.5px] uppercase tracking-[0.06em] text-emerald-700">Most actionable next step</div>
            <p className="mt-1 text-[12.5px] leading-normal text-slate-600">{data.synthesis}</p>
          </div>
        </div>
      )}
      {genError && <ErrorBanner message={genError} onRetry={() => void generate()} />}
    </div>
  );
}
