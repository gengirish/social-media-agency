"use client";

import type { ReactNode } from "react";
import { formatDistanceToNow, isValid, parseISO } from "date-fns";
import { AlertTriangle, Info, Trash2 } from "lucide-react";
import { AD_ROW_LIMITS, type AdSet } from "@/lib/api-ads";
import { cn } from "@/lib/utils";

function Block({ title, children }: { title: ReactNode; children: ReactNode }) {
  return (
    <div>
      <div className="mb-1.5 font-mono text-[9.5px] uppercase tracking-[0.09em] text-muted">{title}</div>
      {children}
    </div>
  );
}

function Row({ text, limit }: { text: string; limit: number }) {
  const over = text.length > limit;
  return (
    <li className="flex items-start justify-between gap-3">
      <span className="text-[12.5px] leading-normal text-slate-600">{text}</span>
      <span
        className={cn("shrink-0 font-mono text-[10px]", over ? "text-red-600" : "text-muted")}
        aria-label={`${text.length} of ${limit} characters${over ? ", over the limit" : ""}`}
      >
        {text.length}/{limit}
      </span>
    </li>
  );
}

function Warning({ tone, children }: { tone: "danger" | "caution"; children: ReactNode }) {
  return (
    <div
      className={cn(
        "mb-3 flex items-start gap-2 rounded-md border px-3 py-2",
        tone === "danger" ? "border-red-300 bg-red-50" : "border-amber-300 bg-amber-50"
      )}
    >
      <AlertTriangle
        aria-hidden
        className={cn("mt-px h-[13px] w-[13px] shrink-0", tone === "danger" ? "text-red-600" : "text-accent-text")}
      />
      <div className="text-[11.5px] leading-normal text-slate-600">{children}</div>
    </div>
  );
}

function ago(iso: string | null): string {
  if (!iso) return "";
  const d = parseISO(iso);
  return isValid(d) ? formatDistanceToNow(d, { addSuffix: true }) : "";
}

/**
 * One generated ad set. The warning blocks come first, above the copy, because
 * someone skimming for something to paste needs to see a trademark or policy
 * problem before they act on it — not after scrolling past 15 headlines.
 */
export function AdSetCard({
  item,
  delay,
  onDelete,
  onCopy,
  copied,
}: {
  item: AdSet;
  delay: number;
  onDelete: (item: AdSet) => void;
  onCopy: (item: AdSet) => void;
  copied: boolean;
}) {
  const p = item.payload;
  const isGoogle = p.network === "google";
  const mod = p.moderation;

  return (
    <article
      className="animate-screen-in rounded-xl border border-line bg-panel/70 p-4 backdrop-blur-xl"
      style={{ animationDelay: `${delay}s` }}
    >
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="text-[13px] font-semibold text-ink">
          {isGoogle ? "Responsive Search Ad" : "Meta ad set"}
          <span className="ml-2 font-mono text-[10px] font-normal text-muted">{ago(item.created_at)}</span>
        </h2>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => onCopy(item)}
            className={cn("text-[11px] font-medium", copied ? "text-emerald-600" : "text-accent-text hover:underline")}
          >
            {copied ? "Copied" : "Copy all"}
          </button>
          <button
            type="button"
            onClick={() => onDelete(item)}
            className="text-muted hover:text-red-600"
            aria-label="Delete ad set"
          >
            <Trash2 className="h-[13px] w-[13px]" />
          </button>
        </div>
      </div>

      {mod?.flagged && mod.issues.length > 0 && (
        <Warning tone="danger">
          <b className="text-ink">Worth a second look — moderation:</b>
          <ul className="mt-1 space-y-0.5">
            {mod.issues.map((iss, i) => (
              <li key={i}>• {iss}</li>
            ))}
          </ul>
        </Warning>
      )}

      {mod?.status === "unavailable" && (
        <div className="mb-3 flex items-start gap-2 rounded-md border border-line bg-slate-500/5 px-3 py-2">
          <Info aria-hidden className="mt-px h-[13px] w-[13px] shrink-0 text-muted" />
          <p className="text-[11.5px] leading-normal text-slate-600">
            The moderation check couldn&apos;t run for this set, so it hasn&apos;t been reviewed for exaggerated
            claims or policy problems. The length, trademark and personal-attribute checks below still ran.
          </p>
        </div>
      )}

      {(p.trademark_risks?.length ?? 0) > 0 && (
        <Warning tone="danger">
          <b className="text-ink">Competitor name in ad text:</b> {p.trademark_risks!.join(", ")}. You can bid on a
          rival&apos;s name as a keyword, but using it in ad copy risks disapproval and, repeated, account suspension.
          Remove it before running this.
        </Warning>
      )}

      {(p.personal_attribute_risks?.length ?? 0) > 0 && (
        <Warning tone="caution">
          <b className="text-ink">Worth a second look — personal attributes:</b> Meta&apos;s most-violated policy bans
          copy implying you know a reader&apos;s personal traits.
          {p.personal_attribute_risks!.map((r, i) => (
            <div key={i} className="mt-1 font-mono text-[10.5px]">
              &ldquo;{r.sentence}&rdquo; — flagged on &ldquo;{r.term}&rdquo;
            </div>
          ))}
          <div className="mt-1 text-muted">
            This is a rough pattern check, not a compliance guarantee — CampaignForge can&apos;t tell you an ad is
            policy-safe.
          </div>
        </Warning>
      )}

      {(p.limit_warnings?.length ?? 0) > 0 && (
        <div className="mb-3 rounded-md border border-line bg-slate-500/5 px-3 py-2">
          <div className="mb-1 text-[11px] font-medium text-muted">Length issues</div>
          {p.limit_warnings!.map((w, i) => (
            <div key={i} className="font-mono text-[10.5px] leading-relaxed text-slate-600">
              {w}
            </div>
          ))}
        </div>
      )}

      {isGoogle ? (
        <div className="space-y-3">
          <Block title={`Headlines (${p.headlines?.length ?? 0})`}>
            <ul className="space-y-1">
              {(p.headlines ?? []).map((h, i) => (
                <Row key={i} text={h} limit={AD_ROW_LIMITS.google.headlines} />
              ))}
            </ul>
          </Block>
          <Block title={`Descriptions (${p.descriptions?.length ?? 0})`}>
            <ul className="space-y-1">
              {(p.descriptions ?? []).map((d, i) => (
                <Row key={i} text={d} limit={AD_ROW_LIMITS.google.descriptions} />
              ))}
            </ul>
          </Block>
          {(p.paths?.length ?? 0) > 0 && (
            <Block title="Display paths">
              <p className="font-mono text-[11.5px] text-slate-600">/{p.paths!.join("/")}</p>
            </Block>
          )}
          {(p.sitelinks?.length ?? 0) > 0 && (
            <Block title="Sitelinks">
              <ul className="space-y-1.5">
                {p.sitelinks!.map((s, i) => (
                  <li key={i}>
                    <span className="text-[12.5px] font-medium text-ink">{s.text}</span>
                    <div className="text-[11.5px] text-muted">
                      {s.desc1} · {s.desc2}
                    </div>
                  </li>
                ))}
              </ul>
            </Block>
          )}
          {(p.callouts?.length ?? 0) > 0 && (
            <Block title="Callouts">
              <div className="flex flex-wrap gap-1.5">
                {p.callouts!.map((c, i) => (
                  <span
                    key={i}
                    className="animate-chip-in rounded border border-line px-[7px] py-0.5 font-mono text-[10.5px] text-slate-600"
                    style={{ animationDelay: `${i * 0.03}s` }}
                  >
                    {c}
                  </span>
                ))}
              </div>
            </Block>
          )}
          {(p.keyword_themes?.length ?? 0) > 0 && (
            <Block title="Keyword themes — one ad group each">
              {p.keyword_themes!.map((k, i) => (
                <div key={i} className="mb-2">
                  <div className="font-mono text-[10px] uppercase tracking-[0.06em] text-accent-text">{k.intent}</div>
                  <div className="text-xs text-slate-600">{(k.keywords ?? []).join(", ")}</div>
                  {k.note && <div className="mt-0.5 text-[11px] text-muted">{k.note}</div>}
                </div>
              ))}
              <div className="mt-1.5 text-[11px] leading-normal text-muted">
                These are themes, not volume-checked keywords — CampaignForge has no Keyword Planner access and
                won&apos;t invent search volumes. Check real volume and bid ranges in Keyword Planner before committing
                budget.
              </div>
            </Block>
          )}
          {(p.negative_keywords?.length ?? 0) > 0 && (
            <Block title="Negative keywords — the biggest waste-saver on a small budget">
              <div className="text-xs leading-relaxed text-slate-600">{p.negative_keywords!.join(", ")}</div>
            </Block>
          )}
          {p.structure_note && (
            <Block title="Campaign structure">
              <p className="text-xs leading-relaxed text-slate-600">{p.structure_note}</p>
            </Block>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          <Block title={`Primary text (${p.primary_texts?.length ?? 0}) — first line is the whole ad`}>
            <ul className="space-y-2">
              {(p.primary_texts ?? []).map((t, i) => (
                <Row key={i} text={t} limit={AD_ROW_LIMITS.meta.primary_texts} />
              ))}
            </ul>
          </Block>
          <Block title={`Headlines (${p.headlines?.length ?? 0})`}>
            <ul className="space-y-1">
              {(p.headlines ?? []).map((h, i) => (
                <Row key={i} text={h} limit={AD_ROW_LIMITS.meta.headlines} />
              ))}
            </ul>
          </Block>
          {(p.descriptions?.length ?? 0) > 0 && (
            <Block title="Link descriptions — often hidden on mobile">
              <ul className="space-y-1">
                {p.descriptions!.map((d, i) => (
                  <Row key={i} text={d} limit={AD_ROW_LIMITS.meta.descriptions} />
                ))}
              </ul>
            </Block>
          )}
          {p.cta && (
            <Block title="CTA button">
              <p className="text-xs leading-relaxed text-slate-600">
                <b className="text-ink">{p.cta}</b>
                {p.cta_reason ? ` — ${p.cta_reason}` : ""}
              </p>
            </Block>
          )}
          {p.creative_direction && (
            <Block title="Creative direction">
              <p className="whitespace-pre-wrap text-xs leading-relaxed text-slate-600">{p.creative_direction}</p>
            </Block>
          )}
          {p.audience_angle && (
            <Block title="Audience angle">
              <p className="text-xs leading-relaxed text-slate-600">{p.audience_angle}</p>
            </Block>
          )}
          {p.special_ad_category_note && (
            <Block title="Special Ad Category check">
              <p className="text-xs leading-relaxed text-slate-600">{p.special_ad_category_note}</p>
            </Block>
          )}
        </div>
      )}
    </article>
  );
}
