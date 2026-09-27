import Link from "next/link";
import type { ReactNode } from "react";
import { Loader2, Sparkles } from "lucide-react";
import { AMPLIFY_MAX_ATOMS, AMPLIFY_PLATFORMS, type Client, type ContentPiece } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Panel } from "@/components/ui/panel";
import { QuotaHint } from "@/components/ui/quota-hint";
import { StatusBadge } from "@/components/ui/status-badge";
import { SOURCE_TYPE_LABEL, type RepurposeSource } from "@/lib/api-create-content";
import { platformLabel } from "./labels";

export type SourceMode = "content" | "asset" | "text";

const FIELD =
  "w-full rounded-md border border-line bg-panel px-3 py-2 text-sm text-ink placeholder:text-muted transition-colors focus:border-accent/60 focus:outline-none disabled:opacity-60";

function Step({ n, title, children, hint }: { n: number; title: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <div className="grid gap-3 md:grid-cols-[11rem_1fr] md:gap-6">
      <div className="flex items-start gap-2.5">
        <span className="mt-px flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-accent/50 font-mono text-[11px] text-accent-text">
          {n}
        </span>
        <div>
          <p className="text-sm font-medium text-ink">{title}</p>
          {hint && <p className="mt-0.5 text-xs text-muted">{hint}</p>}
        </div>
      </div>
      <div className="min-w-0">{children}</div>
    </div>
  );
}

export interface AmplifyFormProps {
  clients: Client[];
  clientsLoading: boolean;
  clientId: string;
  onClientChange: (id: string) => void;
  sourceMode: SourceMode;
  onSourceModeChange: (mode: SourceMode) => void;
  contentItems: ContentPiece[];
  contentLoading: boolean;
  sourceId: string;
  onSourceChange: (id: string) => void;
  /** Saved Create-screen output (Cadence's collectRepurposeSources). */
  assetSources: RepurposeSource[];
  assetLoading: boolean;
  sourceAssetId: string;
  onSourceAssetChange: (id: string) => void;
  sourceText: string;
  onSourceTextChange: (text: string) => void;
  platforms: string[];
  onTogglePlatform: (id: string) => void;
  maxAtoms: number;
  onMaxAtomsChange: (n: number) => void;
  generating: boolean;
  onGenerate: () => void;
  onCancel: () => void;
  generationsUsed?: number | null;
  generationsLimit?: number | null;
  /** Set after a 402 or when the known quota is used up. */
  quotaExhausted: boolean;
  error: string | null;
  /** Disable the inputs while a reviewed pack is on screen. */
  locked?: boolean;
}

export function AmplifyForm(p: AmplifyFormProps) {
  const selected = p.contentItems.find((c) => c.id === p.sourceId);
  const hasSource =
    p.sourceMode === "content"
      ? Boolean(p.sourceId)
      : p.sourceMode === "asset"
        ? Boolean(p.sourceAssetId)
        : p.sourceText.trim().length > 0;
  const canGenerate =
    !p.locked && !p.generating && !p.quotaExhausted && Boolean(p.clientId) && hasSource && p.platforms.length > 0;
  const inputsDisabled = p.generating || p.locked;

  if (!p.clientsLoading && p.clients.length === 0) {
    return (
      <Panel dashed className="p-6 text-sm text-muted">
        Amplify drafts posts for a client, and there are none yet.{" "}
        <Link href="/clients" className="font-medium text-accent-text underline-offset-2 hover:underline">
          Add a client
        </Link>{" "}
        first.
      </Panel>
    );
  }

  return (
    <Panel className="divide-y divide-line">
      <div className="space-y-6 p-4 sm:p-6">
        <Step n={1} title="Client" hint="Brand voice and vocabulary come from its profile.">
          <select
            aria-label="Client"
            className={FIELD}
            value={p.clientId}
            disabled={inputsDisabled || p.clientsLoading}
            onChange={(e) => p.onClientChange(e.target.value)}
          >
            <option value="">{p.clientsLoading ? "Loading clients…" : "Choose a client"}</option>
            {p.clients.map((c) => (
              <option key={c.id} value={c.id}>
                {c.brand_name}
              </option>
            ))}
          </select>
        </Step>

        <Step n={2} title="Source" hint="One real piece of content. Every draft is grounded in it.">
          <div className="space-y-3">
            <div role="radiogroup" aria-label="Source type" className="inline-flex rounded-md border border-line p-0.5">
              {(
                [
                  ["content", "From the queue"],
                  ["asset", "From Create"],
                  ["text", "Paste text"],
                ] as const
              ).map(([mode, label]) => (
                <button
                  key={mode}
                  type="button"
                  role="radio"
                  aria-checked={p.sourceMode === mode}
                  disabled={inputsDisabled}
                  onClick={() => p.onSourceModeChange(mode)}
                  className={cn(
                    "rounded px-3 py-1 text-xs font-medium transition-colors",
                    p.sourceMode === mode ? "bg-accent/15 text-accent-text" : "text-muted hover:text-ink"
                  )}
                >
                  {label}
                </button>
              ))}
            </div>

            {p.sourceMode === "content" ? (
              <>
                <select
                  aria-label="Source content"
                  className={FIELD}
                  value={p.sourceId}
                  disabled={inputsDisabled || !p.clientId || p.contentLoading}
                  onChange={(e) => p.onSourceChange(e.target.value)}
                >
                  <option value="">
                    {!p.clientId
                      ? "Choose a client first"
                      : p.contentLoading
                        ? "Loading content…"
                        : p.contentItems.length === 0
                          ? "This client has no content yet — paste text instead"
                          : "Choose a piece"}
                  </option>
                  {p.contentItems.map((c) => (
                    <option key={c.id} value={c.id}>
                      {platformLabel(c.platform)} · {(c.title || c.body).slice(0, 70) || "Untitled"}
                    </option>
                  ))}
                </select>
                {selected && (
                  <div className="rounded-md border border-line bg-canvas/60 p-3">
                    <div className="mb-1.5 flex items-center gap-2">
                      <span className="text-xs font-medium text-ink">{platformLabel(selected.platform)}</span>
                      <StatusBadge status={selected.status} />
                    </div>
                    <p className="line-clamp-4 whitespace-pre-wrap text-sm text-muted">{selected.body}</p>
                  </div>
                )}
              </>
            ) : p.sourceMode === "asset" ? (
              !p.clientId ? (
                <p className="text-sm text-muted">Choose a client first.</p>
              ) : p.assetLoading ? (
                <p className="text-sm text-muted">Loading saved content…</p>
              ) : p.assetSources.length === 0 ? (
                <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-slate-300 px-4 py-8 text-center font-mono text-xs text-muted">
                  <Sparkles className="h-4 w-4" aria-hidden />
                  Nothing to repurpose yet — generate a blog post, comparison page, niche scan, launch kit or video
                  script in Create first.
                  <Link href="/create/content" className="text-accent-text underline">
                    Go to Create › Content
                  </Link>
                </div>
              ) : (
                <div role="radiogroup" aria-label="Saved content" className="max-h-56 space-y-1.5 overflow-y-auto pr-1">
                  {p.assetSources.map((s) => {
                    const on = p.sourceAssetId === s.id;
                    return (
                      <button
                        key={s.id}
                        type="button"
                        role="radio"
                        aria-checked={on}
                        disabled={inputsDisabled}
                        onClick={() => p.onSourceAssetChange(s.id)}
                        className={cn(
                          "press-scale flex w-full items-center justify-between gap-3 rounded-lg border px-3 py-2.5 text-left transition-all duration-200",
                          on ? "border-accent bg-accent/10" : "border-line hover:border-slate-300"
                        )}
                      >
                        <span className={cn("truncate text-[12.5px] font-medium", on ? "text-ink" : "text-slate-600")}>
                          {s.label}
                        </span>
                        <span className="shrink-0 font-mono text-[9.5px] uppercase text-muted">
                          {SOURCE_TYPE_LABEL[s.kind] ?? s.kind}
                        </span>
                      </button>
                    );
                  })}
                </div>
              )
            ) : (
              <textarea
                aria-label="Source text"
                className={cn(FIELD, "min-h-[9rem] resize-y leading-relaxed")}
                placeholder="Paste a blog post, changelog, launch note, or a good support answer…"
                value={p.sourceText}
                maxLength={20000}
                disabled={inputsDisabled}
                onChange={(e) => p.onSourceTextChange(e.target.value)}
              />
            )}
          </div>
        </Step>

        <Step n={3} title="Platforms" hint="Drafting only. Nothing is published from here.">
          <div className="space-y-3">
            <div className="flex flex-wrap gap-2">
              {AMPLIFY_PLATFORMS.map((pl) => {
                const on = p.platforms.includes(pl.id);
                return (
                  <label
                    key={pl.id}
                    className={cn(
                      "press-scale inline-flex cursor-pointer select-none items-center gap-2 rounded-md border px-3 py-1.5 text-sm transition-colors has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-accent",
                      on ? "border-accent/60 bg-accent/10 text-ink" : "border-line text-muted hover:text-ink",
                      inputsDisabled && "cursor-not-allowed opacity-60"
                    )}
                  >
                    <input
                      type="checkbox"
                      className="sr-only"
                      checked={on}
                      disabled={inputsDisabled}
                      onChange={() => p.onTogglePlatform(pl.id)}
                    />
                    <span
                      aria-hidden
                      className={cn(
                        "h-3 w-3 rounded-sm border",
                        on ? "border-accent bg-accent" : "border-slate-300"
                      )}
                    />
                    {pl.label}
                  </label>
                );
              })}
            </div>
            <label className="flex items-center gap-2 text-sm text-muted">
              Drafts
              <select
                aria-label="Number of drafts"
                className={cn(FIELD, "w-auto py-1")}
                value={p.maxAtoms}
                disabled={inputsDisabled}
                onChange={(e) => p.onMaxAtomsChange(Number(e.target.value))}
              >
                {Array.from({ length: AMPLIFY_MAX_ATOMS }, (_, i) => i + 1).map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
              <span className="text-xs">each a different angle</span>
            </label>
          </div>
        </Step>
      </div>

      <div className="flex flex-wrap items-center gap-3 p-4 sm:px-6">
        <Button onClick={p.onGenerate} disabled={!canGenerate}>
          {p.generating ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> Generating…
            </>
          ) : (
            <>
              <Sparkles className="h-4 w-4" aria-hidden /> Generate pack
            </>
          )}
        </Button>
        {p.generating ? (
          <Button variant="secondary" onClick={p.onCancel}>
            Cancel
          </Button>
        ) : (
          <QuotaHint used={p.generationsUsed} limit={p.generationsLimit} />
        )}
        {p.generating && (
          <p className="basis-full text-xs text-muted">
            Cancel stops the wait. If the server has already finished the pack, it still counts toward your quota.
          </p>
        )}
        {p.quotaExhausted && (
          <p role="alert" className="basis-full text-sm text-red-700">
            You have used every Amplify pack for this billing period.{" "}
            <Link href="/pricing" className="font-medium underline underline-offset-2">
              Upgrade your plan
            </Link>{" "}
            for more.
          </p>
        )}
        {p.error && (
          <p role="alert" className="basis-full text-sm text-red-700">
            {p.error}
          </p>
        )}
      </div>
    </Panel>
  );
}
