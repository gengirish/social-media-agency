import Link from "next/link";
import { CheckCircle2 } from "lucide-react";
import type { AmplifyAtom } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Panel } from "@/components/ui/panel";
import { StatusBadge } from "@/components/ui/status-badge";
import { AtomCard } from "./atom-card";

/**
 * Review step: every atom as a card, each droppable, then one commit for the
 * rest. Nothing reaches the queue until "Add N to queue", and what does lands
 * as Pending — never approved, never scheduled.
 */
export function AtomReview({
  atoms,
  requested,
  discarded,
  dropped,
  onToggle,
  onCommit,
  onDiscard,
  committing,
  committedCount,
}: {
  atoms: AmplifyAtom[];
  /** Atoms asked of the model, and how many it returned unusably (server counts). */
  requested: number;
  discarded: number;
  dropped: Set<number>;
  onToggle: (index: number) => void;
  onCommit: () => void;
  onDiscard: () => void;
  committing: boolean;
  /** Set once the pack is in the queue; the grid becomes read-only. */
  committedCount: number | null;
}) {
  const kept = atoms.length - dropped.size;
  const done = committedCount !== null;

  return (
    <section aria-labelledby="amplify-review" className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 id="amplify-review" className="text-lg font-semibold text-ink">
            Review {atoms.length} {atoms.length === 1 ? "draft" : "drafts"}
          </h2>
          <p className="text-sm text-muted">
            One angle each. Drop anything that misses; the rest go to the queue for approval.
            {discarded > 0 && (
              <>
                {" "}
                {discarded} of {requested} came back unusable (off-format or over the length limit) and were
                discarded.
              </>
            )}
          </p>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {atoms.map((atom, i) => (
          <AtomCard
            key={`${atom.platform}-${atom.angle}`}
            atom={atom}
            dropped={dropped.has(i)}
            onToggle={() => onToggle(i)}
            disabled={committing || done}
          />
        ))}
      </div>

      <Panel className="sticky bottom-4 z-10 flex flex-wrap items-center gap-3 p-3 sm:p-4">
        {done ? (
          <>
            <CheckCircle2 className="h-5 w-5 shrink-0 text-emerald-600" aria-hidden />
            <p className="min-w-0 flex-1 text-sm text-ink">
              {committedCount} {committedCount === 1 ? "draft" : "drafts"} added to the queue as{" "}
              <StatusBadge status="draft" className="align-middle" />
            </p>
            <Link
              href="/content"
              className="press-scale rounded-md border border-line px-3 py-1.5 font-mono text-xs font-medium text-ink transition-colors hover:border-accent/50"
            >
              Open queue
            </Link>
            <Button variant="ghost" size="sm" onClick={onDiscard}>
              Start another
            </Button>
          </>
        ) : (
          <>
            <p className="min-w-0 basis-full text-sm text-muted sm:flex-1 sm:basis-auto">
              <span className="font-medium text-ink">{kept}</span> of {atoms.length} kept · land as{" "}
              <StatusBadge status="draft" className="align-middle" />
            </p>
            <Button variant="ghost" size="sm" className="ml-auto sm:ml-0" onClick={onDiscard} disabled={committing}>
              Discard pack
            </Button>
            <Button onClick={onCommit} disabled={committing || kept === 0}>
              {committing ? "Adding…" : `Add ${kept} to queue`}
            </Button>
          </>
        )}
      </Panel>
    </section>
  );
}
