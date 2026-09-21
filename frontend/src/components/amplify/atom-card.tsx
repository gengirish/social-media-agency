import { AlertTriangle, RotateCcw, X } from "lucide-react";
import type { AmplifyAtom } from "@/lib/api";
import { publishUnavailableReason } from "@/lib/platforms";
import { cn } from "@/lib/utils";
import { Panel } from "@/components/ui/panel";
import { angleLabel, platformLabel } from "./labels";

export function AngleChip({ angle, className }: { angle: string; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border border-accent/40 bg-accent/10 px-2 py-0.5 font-mono text-[11px] font-medium text-accent-text",
        className
      )}
    >
      {angleLabel(angle)}
    </span>
  );
}

/** One generated draft in the review grid. Dropping is reversible until commit. */
export function AtomCard({
  atom,
  dropped,
  onToggle,
  disabled,
}: {
  atom: AmplifyAtom;
  dropped: boolean;
  onToggle: () => void;
  disabled?: boolean;
}) {
  const over = atom.char_count > atom.char_limit;
  const manualOnly = publishUnavailableReason(atom.platform);

  return (
    <Panel
      dashed={dropped}
      role="article"
      className={cn("flex flex-col gap-3 p-4 transition-opacity duration-200", dropped && "opacity-60")}
      aria-label={`${angleLabel(atom.angle)} draft for ${platformLabel(atom.platform)}${dropped ? " (dropped)" : ""}`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <AngleChip angle={atom.angle} />
        <span className="text-xs font-medium text-ink">{platformLabel(atom.platform)}</span>
        <span
          className={cn("ml-auto font-mono text-[11px] tabular-nums", over ? "text-red-600" : "text-muted")}
          title="Published length, hashtags included, against the platform limit"
        >
          {atom.char_count.toLocaleString()} / {atom.char_limit.toLocaleString()}
        </span>
      </div>

      {atom.duplicate_warning && (
        <p className="flex items-start gap-1.5 rounded-md border border-amber-300 bg-amber-50 px-2 py-1.5 text-xs text-amber-800">
          <AlertTriangle className="mt-px h-3.5 w-3.5 shrink-0" aria-hidden />
          Reads a lot like a recent post for this client. Worth a second look.
        </p>
      )}

      <div className={cn("min-w-0 space-y-1.5", dropped && "line-through decoration-slate-400/60")}>
        {atom.title && <p className="text-sm font-semibold text-ink">{atom.title}</p>}
        <p className="whitespace-pre-wrap break-words text-sm leading-relaxed text-ink/90">{atom.body}</p>
        {atom.hashtags.length > 0 && (
          <p className="break-words font-mono text-xs text-muted">{atom.hashtags.map((t) => `#${t}`).join(" ")}</p>
        )}
      </div>

      <div className="mt-auto flex items-center gap-2 border-t border-line pt-3">
        {manualOnly && (
          <span className="text-[11px] text-muted" title={manualOnly}>
            Publish manually
          </span>
        )}
        <button
          type="button"
          onClick={onToggle}
          disabled={disabled}
          aria-pressed={dropped}
          className="press-scale ml-auto inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-muted transition-colors hover:bg-slate-500/10 hover:text-ink disabled:opacity-50"
        >
          {dropped ? (
            <>
              <RotateCcw className="h-3.5 w-3.5" aria-hidden /> Keep
            </>
          ) : (
            <>
              <X className="h-3.5 w-3.5" aria-hidden /> Drop
            </>
          )}
        </button>
      </div>
    </Panel>
  );
}
