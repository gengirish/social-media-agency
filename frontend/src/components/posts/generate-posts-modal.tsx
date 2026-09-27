"use client";

import { useEffect, useState } from "react";
import { Check, Wand2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { PostDialog } from "./dialog";
import { platformLabel, platformTone } from "./platform";

/**
 * Cadence's GeneratePostsModal: pick platforms (all pre-checked), add an
 * optional "what's this post about?" note, generate one Pending draft each.
 * Every draft is one generation, so the button says how many it will use.
 */
export function GeneratePostsModal({
  open,
  platforms,
  remaining,
  title = "Generate post — choose platforms",
  footnote,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  platforms: string[];
  /** Generations left this period, or null when unknown. Caps the selection. */
  remaining: number | null;
  title?: string;
  footnote?: string;
  onConfirm: (platforms: string[], contextNote: string) => void;
  onCancel: () => void;
}) {
  const [selected, setSelected] = useState<string[]>(platforms);
  const [note, setNote] = useState("");

  useEffect(() => {
    if (open) {
      setSelected(platforms);
      setNote("");
    }
  }, [open, platforms]);

  const toggle = (id: string) =>
    setSelected((prev) => (prev.includes(id) ? prev.filter((p) => p !== id) : [...prev, id]));
  const allSelected = selected.length === platforms.length;
  const overQuota = remaining !== null && selected.length > remaining;

  return (
    <PostDialog
      open={open}
      onOpenChange={(o) => !o && onCancel()}
      title={title}
      footer={
        <Button
          className="w-full"
          disabled={selected.length === 0 || overQuota}
          onClick={() => onConfirm(selected, note.trim())}
        >
          <Wand2 className="h-4 w-4" />
          Generate {selected.length > 1 ? `${selected.length} posts` : "post"}
        </Button>
      }
    >
      <label htmlFor="gen-context-note" className="font-mono text-[9.5px] uppercase tracking-[0.1em] text-muted">
        What&apos;s this post actually about? (optional)
      </label>
      <textarea
        id="gen-context-note"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        rows={2}
        maxLength={280}
        placeholder="e.g. the autumn menu launches Friday, we're hiring baristas, early-bird pricing ends soon…"
        className="mt-1.5 w-full resize-none rounded-md border border-line bg-panel px-2.5 py-2 text-[13px] text-ink outline-none transition-[border-color,box-shadow] duration-200 placeholder:text-slate-400 focus:border-accent focus:shadow-[0_0_0_3px_rgb(var(--c-accent)/0.12)]"
      />
      <p className="mt-1 font-mono text-[10px] text-muted">
        Leave blank for a general post — the client&apos;s campaign focus is used if one is set.
      </p>

      <div className="mt-4 space-y-2">
        {platforms.map((id) => {
          const checked = selected.includes(id);
          return (
            <button
              key={id}
              type="button"
              role="checkbox"
              aria-checked={checked}
              onClick={() => toggle(id)}
              className={cn(
                "press-scale flex w-full items-center gap-2.5 rounded-md border px-3 py-2 text-left transition-colors duration-200",
                checked ? "border-accent bg-accent/10" : "border-line"
              )}
            >
              <span
                aria-hidden
                className={cn(
                  "flex h-4 w-4 shrink-0 items-center justify-center rounded border",
                  checked ? "border-accent bg-accent text-on-accent" : "border-slate-300"
                )}
              >
                {checked && <Check className="h-3 w-3" />}
              </span>
              <span aria-hidden className={cn("h-2 w-2 rounded-full", platformTone(id).dot)} />
              <span className={cn("text-[13px] font-medium", checked ? "text-ink" : "text-slate-600")}>
                {platformLabel(id)}
              </span>
            </button>
          );
        })}
      </div>
      <div className="mt-4 flex items-center justify-between text-xs">
        <button
          type="button"
          onClick={() => setSelected(allSelected ? [] : platforms)}
          className="font-medium text-accent-text"
        >
          {allSelected ? "Deselect all" : "Select all"}
        </button>
        <span className="text-muted">
          {selected.length} selected
          {remaining !== null && ` · ${remaining} generation${remaining === 1 ? "" : "s"} left`}
        </span>
      </div>
      {overQuota && (
        <p className="mt-2 text-xs text-red-600">
          That&apos;s more than the generations left this period — pick {remaining} or fewer.
        </p>
      )}
      {footnote && <p className="mt-3 text-xs text-muted">{footnote}</p>}
    </PostDialog>
  );
}
