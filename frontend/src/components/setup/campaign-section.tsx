"use client";

import { useState } from "react";
import { Loader2, Megaphone } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ErrorBanner } from "@/components/ui/feedback";
import { Eyebrow } from "@/components/ui/panel";
import { controlClass } from "@/components/ui/field";
import { useActiveClient } from "@/lib/active-client";
import { foundationApi } from "@/lib/api-foundation";
import { trackFeature } from "@/lib/analytics";
import { cn } from "@/lib/utils";

/**
 * Cadence's CampaignSection: a human-typed standing focus every generator
 * reads (brand_context.brand_prompt_block) until it is changed or cleared.
 * No AI involved. Anchor id `campaign` — CampaignIndicator's Edit links here.
 */
export function CampaignSection({ clientId, focus }: { clientId: string; focus: string | null }) {
  const { refresh } = useActiveClient();
  const [current, setCurrent] = useState<string | null>(focus);
  const [editing, setEditing] = useState(!focus);
  const [draft, setDraft] = useState(focus ?? "");
  const [busy, setBusy] = useState<"save" | "clear" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    const trimmed = draft.trim();
    if (!trimmed) return;
    setBusy("save");
    setError(null);
    try {
      const res = await foundationApi.setCampaignFocus(clientId, trimmed);
      setCurrent(res.campaign_focus);
      setEditing(false);
      trackFeature("campaign-focus");
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save the campaign.");
    } finally {
      setBusy(null);
    }
  };

  const clear = async () => {
    setBusy("clear");
    setError(null);
    try {
      await foundationApi.clearCampaignFocus(clientId);
      setCurrent(null);
      setDraft("");
      setEditing(true);
      toast.success("Campaign cleared — generators are back to the plain brand profile.");
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't clear the campaign.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <section id="campaign" className="scroll-mt-40">
      <Eyebrow>Current campaign / focus (optional)</Eyebrow>
      <p className="mb-3 mt-2 max-w-[560px] text-xs leading-relaxed text-muted">
        Every content-generating agent — posts, blog, email, launch kit, video scripts, community kit, outreach —
        automatically reflects this until you change or clear it. A one-off post can still type its own note to override
        it just for that post; this is the standing default the rest of the time.
      </p>
      {editing ? (
        <div className="flex flex-wrap items-center gap-2">
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && void save()}
            placeholder='e.g. "looking for early testers this month"'
            maxLength={200}
            aria-label="Current campaign or focus"
            className={cn(controlClass, "w-full max-w-[320px] py-1.5 text-[12.5px]")}
          />
          <Button size="sm" onClick={() => void save()} disabled={!draft.trim() || busy !== null}>
            {busy === "save" && <Loader2 className="h-3 w-3 animate-spin" />} Save
          </Button>
          {current && (
            <button
              type="button"
              onClick={() => {
                setDraft(current);
                setEditing(false);
              }}
              className="font-mono text-[11px] text-muted underline"
            >
              Cancel
            </button>
          )}
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-accent/30 bg-accent/5 px-3 py-2.5 motion-safe:animate-chip-in">
          <Megaphone className="h-3.5 w-3.5 shrink-0 text-accent-text" />
          <span className="min-w-[180px] flex-1 text-[12.5px] text-ink">{current}</span>
          <button
            type="button"
            onClick={() => {
              setDraft(current ?? "");
              setEditing(true);
            }}
            className="font-mono text-[11px] text-accent-text underline"
          >
            Edit
          </button>
          <Button size="sm" variant="secondary" onClick={() => void clear()} disabled={busy !== null}>
            {busy === "clear" && <Loader2 className="h-3 w-3 animate-spin" />} Clear
          </Button>
        </div>
      )}
      {error && <ErrorBanner message={error} />}
    </section>
  );
}
