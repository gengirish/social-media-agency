"use client";

import { AlertTriangle } from "lucide-react";
import type { AdVariant } from "@/lib/api";

/**
 * An ad variant rendered in the fields its network actually has.
 *
 * Before this, every ad was shown through the generic post card, whose body is a
 * single paragraph. The pipeline had put `JSON.stringify(headlines)` there, so a
 * Google ad read `["AI Gig Approvals in Days", "Skip Rejected Applications"]` and
 * a Meta or LinkedIn ad — whose copy the model returns under `primary_text`, with
 * no headlines at all — read `[]`. The structure now survives to the UI in
 * `metadata_.ad` (see `services/ad_variants.py`), so headlines can be listed
 * apart from descriptions and each field can carry its own length hint.
 */

/** The fields to show, in order, per network. */
const LAYOUT: Record<AdVariant["platform"], { key: string; label: string; list?: boolean }[]> = {
  google: [
    { key: "headlines", label: "Headlines", list: true },
    { key: "descriptions", label: "Descriptions", list: true },
  ],
  meta: [
    { key: "primary_text", label: "Primary text" },
    { key: "headline", label: "Headline" },
    { key: "description", label: "Description" },
  ],
  linkedin: [
    { key: "intro_text", label: "Intro text" },
    { key: "headline", label: "Headline" },
    { key: "description", label: "Description" },
  ],
};

/** The limit key for a field — the repeated Google fields share one per item. */
function limitKeyFor(field: string): string {
  if (field === "headlines") return "headline";
  if (field === "descriptions") return "description";
  return field;
}

function CharCount({ text, limit }: { text: string; limit?: number }) {
  if (!limit) return null;
  const over = text.length > limit;
  return (
    <span
      className={`ml-2 shrink-0 font-mono text-[10px] ${over ? "text-red-600" : "text-muted"}`}
      // Over-limit copy is flagged, never trimmed: the draft is for a human to
      // edit, and silently cutting a headline would change the agent's output
      // without saying so.
      title={over ? `Over the ${limit}-character limit for this field` : undefined}
    >
      {text.length}/{limit}
    </span>
  );
}

function FieldRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <div className="font-mono text-[10px] uppercase tracking-wide text-muted">{label}</div>
      {children}
    </div>
  );
}

export function AdVariantCard({ ad }: { ad: AdVariant }) {
  if (ad.is_empty) {
    return (
      <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-ink/80">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-600" />
        <span>
          The ad copy agent returned no usable copy for this variant. Re-run the campaign to
          generate it again — it can&apos;t be approved as it is.
        </span>
      </div>
    );
  }

  const rows = LAYOUT[ad.platform] ?? LAYOUT.google;

  return (
    <div className="space-y-3">
      {rows.map(({ key, label, list }) => {
        const value = ad.fields[key as keyof AdVariant["fields"]];
        const limit = ad.limits?.[limitKeyFor(key)];

        if (list) {
          const items = Array.isArray(value) ? value : [];
          if (items.length === 0) return null;
          return (
            <FieldRow key={key} label={label}>
              <ul className="space-y-1">
                {items.map((item, i) => (
                  <li
                    key={i}
                    className="flex items-start justify-between rounded-md bg-canvas/60 px-2.5 py-1.5 text-sm text-ink/90"
                  >
                    <span className="whitespace-pre-wrap">{item}</span>
                    <CharCount text={item} limit={limit} />
                  </li>
                ))}
              </ul>
            </FieldRow>
          );
        }

        const text = typeof value === "string" ? value : "";
        if (!text) return null;
        return (
          <FieldRow key={key} label={label}>
            <div className="flex items-start justify-between rounded-md bg-canvas/60 px-2.5 py-1.5 text-sm text-ink/90">
              <span className="whitespace-pre-wrap">{text}</span>
              <CharCount text={text} limit={limit} />
            </div>
          </FieldRow>
        );
      })}

      {ad.missing.length > 0 && (
        <p className="flex items-start gap-1.5 text-xs text-muted">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600" />
          Missing {ad.missing.join(", ").replace(/_/g, " ")} — add it before this variant runs.
        </p>
      )}

      <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-[10px] text-muted">
        {ad.cta && <span>CTA: {ad.cta}</span>}
        {ad.target_keyword && <span>Keyword: {ad.target_keyword}</span>}
      </div>

      {ad.notes && <p className="text-xs italic text-muted">{ad.notes}</p>}
    </div>
  );
}
