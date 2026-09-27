"use client";

import { useEffect, useRef, useState } from "react";
import { CheckCircle2, Loader2, Wand2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ErrorBanner } from "@/components/ui/feedback";
import { Eyebrow } from "@/components/ui/panel";
import { Input, Textarea } from "@/components/ui/field";
import { QuotaHint } from "@/components/ui/quota-hint";
import { trackFeature } from "@/lib/analytics";
import { setupApi, type BrandVoiceGuide, type SetupProfile } from "@/lib/api-setup";
import { generationErrorMessage } from "./use-generation-quota";

interface Draft {
  voice_description: string;
  dosText: string;
  dontsText: string;
  example_sentence: string;
}

const toDraft = (g: BrandVoiceGuide): Draft => ({
  voice_description: g.voice_description,
  dosText: g.vocabulary_include.join(", "),
  dontsText: g.vocabulary_exclude.join(", "),
  example_sentence: g.example_sentence,
});

const splitList = (s: string) =>
  s
    .split(",")
    .map((w) => w.trim())
    .filter(Boolean);

// A generated draft costs a generation but is only saved on Approve, so keep it
// in this browser until then — a stray navigation should not throw it away.
const DRAFT_KEY = (clientId: string) => `cf-brand-voice-draft-${clientId}`;
function readDraft(clientId: string): Draft | null {
  try {
    const raw = window.localStorage.getItem(DRAFT_KEY(clientId));
    return raw ? (JSON.parse(raw) as Draft) : null;
  } catch {
    return null;
  }
}
function writeDraft(clientId: string, draft: Draft | null) {
  try {
    if (draft) window.localStorage.setItem(DRAFT_KEY(clientId), JSON.stringify(draft));
    else window.localStorage.removeItem(DRAFT_KEY(clientId));
  } catch {
    // Storage blocked: the draft lives in memory for this visit only.
  }
}

const labelClass = "mb-1 font-mono text-[10px] uppercase tracking-[0.08em] text-muted";

/** Cadence's BrandVoiceSection: generate → review/edit → approve into brand_profile. */
export function BrandVoiceSection({
  clientId,
  guide,
  quota,
  onSaved,
}: {
  clientId: string;
  guide: BrandVoiceGuide | null;
  quota: { used: number | null; limit: number | null; reload: () => void };
  onSaved: (profile: SetupProfile) => void;
}) {
  const [draft, setDraft] = useState<Draft | null>(null);
  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    setDraft(readDraft(clientId));
    return () => abortRef.current?.abort();
  }, [clientId]);

  const updateDraft = (next: Draft | null) => {
    setDraft(next);
    writeDraft(clientId, next);
  };

  const generate = async () => {
    const controller = new AbortController();
    abortRef.current = controller;
    setGenerating(true);
    setGenError(null);
    try {
      const result = await setupApi.draftBrandVoice(clientId, controller.signal);
      updateDraft(toDraft(result));
    } catch (e) {
      if (!controller.signal.aborted) setGenError(generationErrorMessage(e, "Couldn't generate the brand voice guide — try again."));
    } finally {
      abortRef.current = null;
      setGenerating(false);
      quota.reload();
    }
  };
  const cancel = () => abortRef.current?.abort();

  const approve = async () => {
    if (!draft) return;
    setSaving(true);
    setSaveError(null);
    try {
      const profile = await setupApi.approveBrandVoice(clientId, {
        voice_description: draft.voice_description.trim(),
        vocabulary_include: splitList(draft.dosText),
        vocabulary_exclude: splitList(draft.dontsText),
        example_sentence: draft.example_sentence.trim(),
      });
      updateDraft(null);
      onSaved(profile);
      toast.success("Brand voice approved");
      trackFeature("brand-voice");
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "Couldn't save the brand voice.");
    } finally {
      setSaving(false);
    }
  };

  if (draft) {
    return (
      <div className="motion-safe:animate-screen-in">
        <Eyebrow>Brand voice guide — review before approving</Eyebrow>
        <div className="mt-3 max-w-[560px] space-y-3">
          <div>
            <div className={labelClass}>Voice description</div>
            <Textarea
              rows={3}
              value={draft.voice_description}
              onChange={(e) => updateDraft({ ...draft, voice_description: e.target.value })}
              aria-label="Voice description"
              className="text-[12.5px]"
            />
          </div>
          <div>
            <div className={labelClass}>Use words like (comma-separated)</div>
            <Input
              value={draft.dosText}
              onChange={(e) => updateDraft({ ...draft, dosText: e.target.value })}
              aria-label="Words to use"
              className="text-[12.5px]"
            />
          </div>
          <div>
            <div className={labelClass}>Never use (comma-separated)</div>
            <Input
              value={draft.dontsText}
              onChange={(e) => updateDraft({ ...draft, dontsText: e.target.value })}
              aria-label="Words never to use"
              className="text-[12.5px]"
            />
          </div>
          <div>
            <div className={labelClass}>Example sentence in this voice</div>
            <Input
              value={draft.example_sentence}
              onChange={(e) => updateDraft({ ...draft, example_sentence: e.target.value })}
              aria-label="Example sentence"
              className="text-[12.5px]"
            />
          </div>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Button size="sm" onClick={() => void approve()} disabled={saving || generating || !draft.voice_description.trim()}>
            {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <CheckCircle2 className="h-3 w-3" />} Approve brand voice
          </Button>
          <Button size="sm" variant="secondary" onClick={() => void generate()} disabled={generating || saving}>
            {generating ? (
              <>
                <Loader2 className="h-3 w-3 animate-spin" /> Regenerating…
              </>
            ) : (
              "Regenerate"
            )}
          </Button>
          {generating ? (
            <button type="button" onClick={cancel} className="font-mono text-[11px] text-muted underline">
              Cancel
            </button>
          ) : (
            <Button size="sm" variant="secondary" onClick={() => updateDraft(null)} disabled={saving}>
              Cancel
            </Button>
          )}
          <QuotaHint used={quota.used} limit={quota.limit} className="ml-1" />
        </div>
        {genError && <ErrorBanner message={genError} onRetry={() => void generate()} />}
        {saveError && <ErrorBanner message={saveError} onRetry={() => void approve()} />}
      </div>
    );
  }

  if (guide) {
    return (
      <div className="motion-safe:animate-screen-in">
        <div className="flex items-center gap-2">
          <Eyebrow>Brand voice guide</Eyebrow>
          <CheckCircle2 className="h-3 w-3 text-accent-text" aria-label="Approved" />
          <button
            type="button"
            onClick={() => updateDraft(toDraft(guide))}
            className="ml-auto font-mono text-[11px] text-muted underline"
          >
            Edit
          </button>
        </div>
        {guide.voice_description && (
          <p className="mt-2 max-w-[560px] text-[12.5px] leading-relaxed text-slate-600">{guide.voice_description}</p>
        )}
        <div className="mt-2 flex flex-wrap gap-1.5">
          {guide.vocabulary_include.map((w, i) => (
            <span
              key={`do-${w}`}
              style={{ animationDelay: `${i * 0.03}s` }}
              className="rounded border border-emerald-300 px-1.5 py-0.5 font-mono text-[10px] text-emerald-700 motion-safe:animate-chip-in"
            >
              {w}
            </span>
          ))}
          {guide.vocabulary_exclude.map((w, i) => (
            <span
              key={`dont-${w}`}
              style={{ animationDelay: `${(guide.vocabulary_include.length + i) * 0.03}s` }}
              className="rounded border border-red-300 px-1.5 py-0.5 font-mono text-[10px] text-red-600 line-through motion-safe:animate-chip-in"
            >
              {w}
            </span>
          ))}
        </div>
        {guide.example_sentence && (
          <p className="mt-2 font-mono text-[11.5px] italic text-muted">&ldquo;{guide.example_sentence}&rdquo;</p>
        )}
        <p className="mt-3 max-w-[560px] text-[11px] leading-normal text-muted">
          Every content-generating agent (social posts, blog, email, launch copy) now reads this automatically — no
          per-agent setup needed.
        </p>
      </div>
    );
  }

  return (
    <div>
      <Eyebrow>Brand voice guide (optional)</Eyebrow>
      <p className="mb-3 mt-2 max-w-[560px] text-xs leading-relaxed text-muted">
        Your Voice answer above is a coarse register — one of 4 options. Every content-generating agent can instead
        follow a fuller guide: vocabulary to use, vocabulary to avoid, and one example sentence as a north star, so a
        blog post and a LinkedIn post for this client actually sound like the same brand.
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <Button size="sm" onClick={() => void generate()} disabled={generating}>
          {generating ? (
            <>
              <Loader2 className="h-3 w-3 animate-spin" /> Drafting…
            </>
          ) : (
            <>
              <Wand2 className="h-3 w-3" /> Generate brand voice guide
            </>
          )}
        </Button>
        {generating && (
          <button type="button" onClick={cancel} className="font-mono text-[11px] text-muted underline">
            Cancel
          </button>
        )}
        <QuotaHint used={quota.used} limit={quota.limit} />
      </div>
      {genError && <ErrorBanner message={genError} onRetry={() => void generate()} />}
    </div>
  );
}
