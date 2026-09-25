"use client";

/*
 * Cadence's Customer Advocacy agent, embedded in Insights next to the real stats
 * it is grounded in. The server hands the model only real counts and rejects any
 * reply that cites a number it did not supply (502, no quota used). Each result
 * is saved as a creative asset (kind "advocacy"); the three most recent show here.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Check, Copy, Loader2, Wand2 } from "lucide-react";
import { api, isGenerationQuotaError } from "@/lib/api";
import { foundationApi, type ClientOverview, type CreativeAsset } from "@/lib/api-foundation";
import { insightsApi, type AdvocacyPayload } from "@/lib/api-insights";
import { trackFeature } from "@/lib/analytics";
import { Button } from "@/components/ui/button";
import { Eyebrow, Panel } from "@/components/ui/panel";
import { ErrorBanner } from "@/components/ui/feedback";
import { QuotaHint } from "@/components/ui/quota-hint";

const SHOWN = 3;

export function AdvocacyPanel({ client, publishedCount }: { client: ClientOverview; publishedCount: number }) {
  const [items, setItems] = useState<CreativeAsset<AdvocacyPayload>[]>([]);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [quota, setQuota] = useState<{ used?: number; limit?: number }>({});
  const [copied, setCopied] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const loadQuota = useCallback(async () => {
    try {
      const sub = await api.getSubscription();
      setQuota({ used: sub.generations_used, limit: sub.generations_limit });
    } catch {
      setQuota({});
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    foundationApi
      .listAssets<AdvocacyPayload>({ clientId: client.id, kinds: ["advocacy"], limit: SHOWN })
      .then((res) => !cancelled && setItems(res.items))
      .catch(() => !cancelled && setItems([]));
    void loadQuota();
    return () => {
      cancelled = true;
    };
  }, [client.id, loadQuota]);

  const atLimit = quota.used != null && quota.limit != null && quota.used >= quota.limit;
  const needsProfile = !client.has_brand_profile;

  const generate = async () => {
    if (atLimit || needsProfile) return;
    setGenerating(true);
    setError(null);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const asset = await insightsApi.generateAdvocacy(client.id, controller.signal);
      setItems((prev) => [asset, ...prev].slice(0, SHOWN));
      trackFeature("customer-advocacy");
      void loadQuota();
    } catch (err) {
      if (controller.signal.aborted) return;
      if (isGenerationQuotaError(err)) {
        void loadQuota();
        setError("quota");
      } else {
        setError("failed");
      }
    } finally {
      abortRef.current = null;
      setGenerating(false);
    }
  };

  const copy = (key: string, text: string) => {
    void navigator.clipboard?.writeText(text).then(() => {
      setCopied(key);
      setTimeout(() => setCopied(null), 1600);
    });
  };

  return (
    <Panel dashed className="p-6 motion-safe:animate-screen-in" style={{ animationDelay: "0.2s" }}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <Eyebrow>Customer advocacy agent</Eyebrow>
          <p className="mt-1 max-w-lg text-[11.5px] text-muted">
            Turns the real numbers above into a review request, a case study outline, and a shareable proof
            line — grounded in what actually happened ({publishedCount} published), not invented growth claims.
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <QuotaHint used={quota.used} limit={quota.limit} />
          <Button size="sm" onClick={() => void generate()} disabled={generating || atLimit || needsProfile}>
            {generating ? (
              <>
                <Loader2 className="h-3 w-3 animate-spin" /> Writing…
              </>
            ) : (
              <>
                <Wand2 className="h-3 w-3" /> Generate
              </>
            )}
          </Button>
          {generating && (
            <button
              type="button"
              onClick={() => abortRef.current?.abort()}
              className="font-mono text-[11px] text-muted underline"
            >
              Cancel
            </button>
          )}
        </div>
      </div>

      {needsProfile ? (
        <p className="mt-3 text-xs text-muted">
          Set up {client.brand_name}&apos;s brand profile first so the voice is right.{" "}
          <Link href="/setup/profile" className="text-accent-text underline">
            Go to Profile
          </Link>
        </p>
      ) : atLimit || error === "quota" ? (
        <ErrorBanner
          message={
            <>
              You&apos;ve used all {quota.limit ?? ""} generations this billing period.{" "}
              <Link href="/settings?tab=plan" className="underline">
                See plan &amp; usage
              </Link>
            </>
          }
        />
      ) : (
        error === "failed" && (
          <ErrorBanner message="Couldn't generate advocacy content — no quota was used." onRetry={() => void generate()} />
        )
      )}

      {items.length > 0 && (
        <div className="mt-4 space-y-3">
          {items.map((item, i) => (
            <div
              key={item.id}
              className="rounded-lg border border-line bg-canvas/40 p-4 motion-safe:animate-pop-in"
              style={{ animationDelay: `${i * 0.04}s` }}
            >
              <div className="grid gap-3 md:grid-cols-2">
                <Field
                  label="Review request"
                  text={item.payload.reviewRequestMessage}
                  copied={copied === `${item.id}-r`}
                  onCopy={() => copy(`${item.id}-r`, item.payload.reviewRequestMessage)}
                />
                <Field
                  label="Social proof line"
                  text={item.payload.socialProofSnippet}
                  copied={copied === `${item.id}-p`}
                  onCopy={() => copy(`${item.id}-p`, item.payload.socialProofSnippet)}
                />
              </div>
              <div className="mt-3">
                <div className="font-mono text-[9.5px] uppercase tracking-[0.06em] text-muted">Case study outline</div>
                <ul className="mt-1 space-y-0.5">
                  {(item.payload.caseStudyOutline ?? []).map((h, idx) => (
                    <li key={idx} className="text-xs text-slate-600">
                      {idx + 1}. {h}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}

function Field({
  label,
  text,
  copied,
  onCopy,
}: {
  label: string;
  text: string;
  copied: boolean;
  onCopy: () => void;
}) {
  return (
    <div>
      <div className="flex items-center justify-between">
        <div className="font-mono text-[9.5px] uppercase tracking-[0.06em] text-muted">{label}</div>
        <button
          type="button"
          onClick={onCopy}
          aria-label={`Copy ${label.toLowerCase()}`}
          className={copied ? "press-scale text-emerald-600" : "press-scale text-muted hover:text-ink"}
        >
          {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
        </button>
      </div>
      <p className="mt-0.5 text-xs leading-normal text-slate-600">{text}</p>
    </div>
  );
}
