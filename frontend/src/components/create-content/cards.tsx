"use client";

/*
 * Cadence's SEOContentCard / ComparisonPageCard / NicheScanCard /
 * VideoScriptCard. Long-form output has no platform and no approve/schedule/
 * publish states — it is copied or exported and published wherever the
 * client's blog or channel lives.
 */

import { useState, type ReactNode } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  ExternalLink,
  FileText,
  Loader2,
  Scan,
  Sparkle,
  Trash2,
  Wand2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Panel } from "@/components/ui/panel";
import { cn } from "@/lib/utils";
import type {
  BlogPayload,
  ComparisonPayload,
  NicheScanPayload,
  VideoScriptPayload,
  WebResearch,
} from "@/lib/api-create-content";

interface CardShellProps {
  delay: number;
  chip: ReactNode;
  title: ReactNode;
  sub: ReactNode;
  deleteLabel: string;
  onDelete: () => void;
  children?: ReactNode;
}

function CardShell({ delay, chip, title, sub, deleteLabel, onDelete, children }: CardShellProps) {
  return (
    <Panel className="p-5 motion-safe:animate-screen-in" style={{ animationDelay: `${delay}s` }}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <span className="inline-flex items-center gap-1 rounded border border-accent/30 px-2 py-0.5 font-mono text-[9.5px] uppercase tracking-[0.05em] text-accent-text">
            {chip}
          </span>
          <h3 className="mt-2 text-[15px] font-semibold text-ink">{title}</h3>
          <p className="mt-1 text-xs leading-normal text-muted">{sub}</p>
        </div>
        <button
          type="button"
          onClick={onDelete}
          aria-label={deleteLabel}
          className="press-scale shrink-0 text-muted hover:text-red-600"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
      {children}
    </Panel>
  );
}

function Label({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("mb-1.5 font-mono text-[10px] uppercase tracking-[0.08em] text-muted", className)}>
      {children}
    </div>
  );
}

function Expanded({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("mt-4 motion-safe:animate-screen-in", className)}>{children}</div>;
}

interface ActionsProps {
  expanded: boolean;
  onToggle: () => void;
  readLabel: string;
  copyLabel: string;
  copied: boolean;
  onCopy: () => void;
  onExport: () => void;
  children?: ReactNode;
  trailing?: ReactNode;
}

function Actions({ expanded, onToggle, readLabel, copyLabel, copied, onCopy, onExport, children, trailing }: ActionsProps) {
  return (
    <div className="mt-4 flex flex-wrap items-center gap-2">
      <Button size="sm" variant="secondary" onClick={onToggle} aria-expanded={expanded}>
        {expanded ? "Collapse" : readLabel}
      </Button>
      <Button size="sm" onClick={onCopy}>
        {copied ? (
          <>
            <CheckCircle2 className="h-3 w-3" /> Copied
          </>
        ) : (
          <>
            <FileText className="h-3 w-3" /> {copyLabel}
          </>
        )}
      </Button>
      <button
        type="button"
        onClick={onExport}
        aria-label="Download as a Markdown file"
        title="Download as .md"
        className="press-scale text-muted hover:text-ink"
      >
        <Download className="h-[13px] w-[13px]" />
      </button>
      {children}
      {trailing && <span className="ml-auto font-mono text-[10px] text-muted">{trailing}</span>}
    </div>
  );
}

/** Whether live web search really ran — stamped server-side, never inferred from the model. */
function ResearchNote({ research, note }: { research?: WebResearch; note?: string }) {
  if (!research && !note) return null;
  const live = research?.status === "ok";
  return (
    <div className="mt-3 space-y-1.5">
      {research && !live && (
        <p className="flex items-start gap-1.5 text-[11px] leading-normal text-amber-700">
          <AlertTriangle aria-hidden className="mt-px h-3 w-3 shrink-0" />
          No live web data — written without browsing. Verify every point about a named competitor.
        </p>
      )}
      {note && <p className="text-[11px] leading-normal text-muted">{note}</p>}
      {live && research.sources.length > 0 && (
        <ul className="space-y-0.5">
          {research.sources.map((s) => (
            <li key={s.url} className="truncate text-[11px]">
              <a
                href={s.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-muted underline-offset-2 hover:text-ink hover:underline"
              >
                <ExternalLink aria-hidden className="h-2.5 w-2.5 shrink-0" />
                <span className="font-mono text-[10px]">{s.competitor}</span> · {s.title}
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function CancelLink({ onClick }: { onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} className="font-mono text-[11px] text-muted underline">
      Cancel
    </button>
  );
}

interface CommonProps {
  delay: number;
  copied: boolean;
  onDelete: () => void;
  onCopy: () => void;
  onExport: () => void;
}

export function BlogCard({
  item,
  optimizing,
  aiSeoError,
  onOptimize,
  onCancelOptimize,
  ...c
}: CommonProps & {
  item: BlogPayload;
  optimizing: boolean;
  aiSeoError: boolean;
  onOptimize: () => void;
  onCancelOptimize: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <CardShell
      delay={c.delay}
      chip={item.keyword}
      title={item.title}
      sub={item.metaDescription}
      deleteLabel="Delete this content piece"
      onDelete={c.onDelete}
    >
      {expanded && (
        <Expanded>
          {item.fromGap && (
            <p className="mb-3 text-[11px] text-muted">
              Written from a niche-scan gap: <span className="text-slate-600">{item.fromGap}</span>
            </p>
          )}
          <Label>Outline</Label>
          <ol className="mb-4 space-y-1">
            {item.outline.map((h, i) => (
              <li key={i} className="flex items-start gap-1.5 text-[12.5px] text-slate-600">
                <span className="text-muted">{i + 1}.</span> {h}
              </li>
            ))}
          </ol>
          <Label>Draft</Label>
          <p className="whitespace-pre-wrap text-[13px] leading-[1.7] text-slate-600">{item.body}</p>

          {item.aiSeoPack && (
            <div className="mt-5 rounded-lg border border-sky-300/60 bg-sky-500/5 p-4">
              <div className="mb-2 flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.08em] text-sky-700">
                <Sparkle aria-hidden className="h-[11px] w-[11px]" /> Optimized for AI search
              </div>
              <Label className="mb-0 text-[9.5px] tracking-[0.06em]">Citable summary</Label>
              <p className="mb-3 mt-1 text-[12.5px] leading-relaxed text-slate-600">{item.aiSeoPack.citableSummary}</p>
              <Label className="mb-0 text-[9.5px] tracking-[0.06em]">FAQ block</Label>
              <div className="mb-3 mt-1 space-y-2">
                {item.aiSeoPack.faq.map((qa, i) => (
                  <div key={i}>
                    <div className="text-[12.5px] font-semibold text-ink">{qa.question}</div>
                    <div className="text-xs leading-normal text-slate-600">{qa.answer}</div>
                  </div>
                ))}
              </div>
              <Label className="mb-0 text-[9.5px] tracking-[0.06em]">Entity clarity</Label>
              <p className="mb-3 mt-1 text-xs leading-normal text-slate-600">{item.aiSeoPack.entityClarityNotes}</p>
              <Label className="mb-0 text-[9.5px] tracking-[0.06em]">Suggested llms.txt entry</Label>
              <code className="mt-1 block whitespace-pre-wrap font-mono text-[11px] text-slate-600">
                {item.aiSeoPack.llmsTxtEntry}
              </code>
            </div>
          )}
        </Expanded>
      )}

      <Actions
        expanded={expanded}
        onToggle={() => setExpanded((v) => !v)}
        readLabel="Read full draft"
        copyLabel="Copy draft"
        copied={c.copied}
        onCopy={c.onCopy}
        onExport={c.onExport}
        trailing={item.searchIntent}
      >
        {!item.aiSeoPack && (
          <Button size="sm" variant="secondary" disabled={optimizing} onClick={onOptimize}>
            {optimizing ? (
              <>
                <Loader2 className="h-3 w-3 animate-spin" /> Optimizing…
              </>
            ) : (
              <>
                <Sparkle className="h-3 w-3" /> Optimize for AI search
              </>
            )}
          </Button>
        )}
        {optimizing && <CancelLink onClick={onCancelOptimize} />}
      </Actions>
      {aiSeoError && (
        <p role="alert" className="mt-2 flex items-center gap-2 font-mono text-[11px] text-red-700">
          Couldn&apos;t generate the AI-search optimization pack.
          <button type="button" onClick={onOptimize} className="text-ink underline">
            Try again
          </button>
        </p>
      )}
    </CardShell>
  );
}

export function ComparisonCard({ item, ...c }: CommonProps & { item: ComparisonPayload }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <CardShell
      delay={c.delay}
      chip={`vs ${item.competitorName}`}
      title={item.title}
      sub={item.metaDescription}
      deleteLabel="Delete this comparison page"
      onDelete={c.onDelete}
    >
      {expanded && (
        <Expanded>
          <p className="mb-4 text-[13px] leading-[1.7] text-slate-600">{item.introParagraph}</p>
          <Label>Comparison points</Label>
          <div className="mb-4 space-y-2.5">
            {item.comparisonPoints.map((p, i) => (
              <div key={i} className="rounded-md border border-line bg-slate-500/[0.03] p-3">
                <div className="mb-1 text-xs font-semibold text-ink">{p.dimension}</div>
                <div className="flex gap-4">
                  <div className="flex-1">
                    <span className="font-mono text-[9.5px] text-emerald-600">US</span>
                    <p className="mt-0.5 text-xs text-slate-600">{p.us}</p>
                  </div>
                  <div className="flex-1">
                    <span className="font-mono text-[9.5px] text-muted">THEM</span>
                    <p className="mt-0.5 text-xs text-slate-600">{p.them}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
          <Label>Where they honestly win</Label>
          <p className="mb-4 text-[13px] leading-[1.7] text-slate-600">{item.honestWhereTheyWin}</p>
          <Label>CTA</Label>
          <p className="text-[13px] leading-[1.7] text-slate-600">{item.cta}</p>
          <ResearchNote research={item.webResearch} note={item.sourcesNote} />
        </Expanded>
      )}
      {!expanded && item.webResearch?.status === "unavailable" && (
        <p className="mt-3 flex items-center gap-1.5 text-[11px] text-amber-700">
          <AlertTriangle aria-hidden className="h-3 w-3" /> No live web data
        </p>
      )}
      <Actions
        expanded={expanded}
        onToggle={() => setExpanded((v) => !v)}
        readLabel="Read full page"
        copyLabel="Copy draft"
        copied={c.copied}
        onCopy={c.onCopy}
        onExport={c.onExport}
      />
    </CardShell>
  );
}

const SATURATION: Record<string, string> = {
  high: "border-red-400 text-red-600",
  medium: "border-accent/60 text-accent-text",
  low: "border-emerald-500 text-emerald-600",
};

export function NicheScanCard({
  item,
  generatingGap,
  gapError,
  onGenerateFromGap,
  onCancelGap,
  ...c
}: CommonProps & {
  item: NicheScanPayload;
  generatingGap: boolean;
  gapError: boolean;
  onGenerateFromGap: () => void;
  onCancelGap: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const scanned = item.scannedAt ? new Date(item.scannedAt).toLocaleDateString() : "";
  return (
    <CardShell
      delay={c.delay}
      chip={
        <>
          <Scan aria-hidden className="h-2.5 w-2.5" /> {item.competitorNames.length} competitors scanned
        </>
      }
      title={`vs ${item.competitorNames.join(", ")}`}
      sub={`${item.angles.length} angles found${scanned ? ` · ${scanned}` : ""}`}
      deleteLabel="Delete this niche scan"
      onDelete={c.onDelete}
    >
      {expanded && (
        <Expanded>
          <div className="mb-1.5 text-[11px] font-medium text-muted">Angles in this niche</div>
          <div className="mb-4 space-y-2.5">
            {item.angles.map((a, i) => (
              <div
                key={i}
                className="rounded-md border border-line bg-slate-500/[0.03] p-3 motion-safe:animate-chip-in"
                style={{ animationDelay: `${i * 0.04}s` }}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="text-xs font-semibold text-ink">{a.angle}</div>
                  <span
                    className={cn(
                      "shrink-0 rounded border px-1.5 py-px text-[9.5px] font-semibold uppercase",
                      SATURATION[a.saturation] ?? "border-line text-muted"
                    )}
                  >
                    {a.saturation} saturation
                  </span>
                </div>
                <div className="mt-1 text-[10.5px] text-muted">Used by: {a.usedBy.join(", ") || "—"}</div>
                {a.note && <p className="mt-1 text-xs text-slate-600">{a.note}</p>}
              </div>
            ))}
          </div>
          <div className="rounded-md border border-emerald-400/50 bg-emerald-500/5 p-3">
            <div className="mb-1 text-[11px] font-medium text-emerald-700">Gap to consider</div>
            <p className="text-[13px] leading-relaxed text-slate-600">{item.gapRecommendation}</p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Button size="sm" onClick={onGenerateFromGap} disabled={generatingGap}>
                {generatingGap ? (
                  <>
                    <Loader2 className="h-3 w-3 animate-spin" /> Writing…
                  </>
                ) : (
                  <>
                    <Wand2 className="h-3 w-3" /> Generate blog post from this gap
                  </>
                )}
              </Button>
              {generatingGap && <CancelLink onClick={onCancelGap} />}
              {gapError && (
                <span role="alert" className="text-[11px] text-red-600">
                  Couldn&apos;t generate — try again
                </span>
              )}
            </div>
          </div>
          <ResearchNote research={item.webResearch} note={item.sourcesNote} />
        </Expanded>
      )}
      {!expanded && item.webResearch?.status === "unavailable" && (
        <p className="mt-3 flex items-center gap-1.5 text-[11px] text-amber-700">
          <AlertTriangle aria-hidden className="h-3 w-3" /> No live web data
        </p>
      )}
      <Actions
        expanded={expanded}
        onToggle={() => setExpanded((v) => !v)}
        readLabel="See full scan"
        copyLabel="Copy summary"
        copied={c.copied}
        onCopy={c.onCopy}
        onExport={c.onExport}
      />
    </CardShell>
  );
}

export function VideoScriptCard({ item, ...c }: CommonProps & { item: VideoScriptPayload }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <CardShell
      delay={c.delay}
      chip="Script · hook"
      title={item.hook}
      sub={item.caption}
      deleteLabel="Delete this script"
      onDelete={c.onDelete}
    >
      {expanded && (
        <Expanded className="space-y-3">
          <div>
            <Label className="mb-1">Script beats</Label>
            <ol className="space-y-1">
              {item.scriptBeats.map((b, i) => (
                <li key={i} className="text-[12.5px] text-slate-600">
                  {i + 1}. {b}
                </li>
              ))}
            </ol>
          </div>
          <div>
            <Label className="mb-1">On-screen text</Label>
            {item.onScreenText.map((t, i) => (
              <div key={i} className="text-[12.5px] text-slate-600">
                &ldquo;{t}&rdquo;
              </div>
            ))}
          </div>
          <div>
            <Label className="mb-0">Audio style</Label>
            <div className="mt-0.5 text-[12.5px] text-slate-600">{item.audioStyleNote}</div>
          </div>
          <div>
            <Label className="mb-0">Hashtags</Label>
            <div className="mt-0.5 text-[12.5px] text-slate-600">{item.hashtags.map((h) => `#${h}`).join(" ")}</div>
          </div>
        </Expanded>
      )}
      <Actions
        expanded={expanded}
        onToggle={() => setExpanded((v) => !v)}
        readLabel="View full script"
        copyLabel="Copy script"
        copied={c.copied}
        onCopy={c.onCopy}
        onExport={c.onExport}
        trailing="Script only — you film it"
      />
    </CardShell>
  );
}
