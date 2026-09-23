import { format } from "date-fns";
import type { AmplifyPack } from "@/lib/api";
import { Panel } from "@/components/ui/panel";
import { platformLabel } from "./labels";

function sourceLabel(pack: AmplifyPack): string {
  if (pack.source_content_id) return pack.source_title?.trim() || "Content piece (untitled)";
  if (pack.source_asset_id) return pack.source_title?.trim() || "Saved content (untitled)";
  if (pack.source_excerpt) return `“${pack.source_excerpt}${pack.source_excerpt.length >= 140 ? "…" : ""}”`;
  // A content-sourced pack stores no text, so once its source piece is deleted
  // (FK is ON DELETE SET NULL) there is nothing left to show.
  return "Source deleted";
}

/** Recent packs for the workspace. Counts are straight from the pack rows. */
export function PackHistory({ packs, loading }: { packs: AmplifyPack[]; loading: boolean }) {
  return (
    <section aria-labelledby="amplify-history" className="space-y-3">
      <h2 id="amplify-history" className="text-lg font-semibold text-ink">
        Recent packs
      </h2>
      <Panel className="overflow-hidden">
        {loading ? (
          <p className="p-4 text-sm text-muted">Loading…</p>
        ) : packs.length === 0 ? (
          <p className="p-4 text-sm text-muted">No packs yet. Generated packs show up here, whether or not you kept them.</p>
        ) : (
          <ul className="divide-y divide-line">
            {packs.map((pack) => (
              <li key={pack.id} className="flex flex-col gap-1 px-4 py-3 sm:flex-row sm:items-center sm:gap-4">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-ink">{sourceLabel(pack)}</p>
                  <p className="truncate text-xs text-muted">
                    {pack.client_name ?? "Client"} · {pack.platforms.map(platformLabel).join(", ")}
                  </p>
                </div>
                <p className="shrink-0 font-mono text-xs text-muted">
                  {pack.atom_count} generated ·{" "}
                  <span className={pack.committed_count > 0 ? "text-ink" : undefined}>
                    {pack.committed_count > 0 ? `${pack.committed_count} queued` : "not queued"}
                  </span>
                </p>
                {pack.created_at && (
                  <time dateTime={pack.created_at} className="shrink-0 font-mono text-xs text-muted">
                    {format(new Date(pack.created_at), "d MMM, HH:mm")}
                  </time>
                )}
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </section>
  );
}
