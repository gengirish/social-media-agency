"use client";

/*
 * Cadence's IntakeScreen for one client: URL scan → clarifying Q&A with
 * push-back coaching → review → approve. Back/Cancel on every step.
 *
 * The scan is the real website read (POST /magic-brief). The findings list
 * shows what is being looked for while the request is in flight — spinners
 * only, nothing ticked — and each row is ticked with the value actually found
 * once the response arrives. No timer pretends to have found anything.
 */

import { useEffect, useRef, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  CheckCircle2,
  FileText,
  Lightbulb,
  Loader2,
  Minus,
  Scan,
  Search,
  Sparkle,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ConfirmDialog, ErrorBanner } from "@/components/ui/feedback";
import { Eyebrow, Panel } from "@/components/ui/panel";
import { trackFeature } from "@/lib/analytics";
import type { BrandProfile } from "@/lib/api";
import { TONE_REGISTERS, setupApi, type AnswerCoaching, type IntakeAnswers, type SetupProfile } from "@/lib/api-setup";
import { cn } from "@/lib/utils";

type Step = 0 | 1 | 2 | 3;
type TextQuestionId = "audience" | "differentiator";

interface Question {
  id: keyof IntakeAnswers;
  label: string;
  placeholder?: string;
  options?: readonly string[];
}

const QUESTIONS: Question[] = [
  { id: "audience", label: "Who is this client actually for?", placeholder: "e.g. independent coffee roasters with one shop" },
  {
    id: "differentiator",
    label: "What makes it different from the closest alternative?",
    placeholder: "e.g. roast-to-door in 48 hours, no subscription",
  },
  { id: "tone", label: "How should it sound on social — pick a register", options: TONE_REGISTERS },
];

/** What the scan looks for, and which field of the Magic Brief response answers it. */
const SCAN_ROWS: { key: keyof BrandProfile; looking: string; found: string }[] = [
  { key: "brand_name", looking: "Reading the page", found: "Brand" },
  { key: "description", looking: "Working out what it does", found: "What it does" },
  { key: "target_audience", looking: "Estimating target audience", found: "Audience" },
  { key: "competitor_differentiation", looking: "Looking for what sets it apart", found: "Differentiator" },
  { key: "content_pillars", looking: "Scanning the topics it covers", found: "Topics" },
];

function scanValue(result: BrandProfile, key: keyof BrandProfile): string {
  const v = result[key];
  if (Array.isArray(v)) return v.filter((x) => typeof x === "string" && x.trim()).join(", ");
  return typeof v === "string" ? v.trim() : "";
}

export const isLikelyUrl = (s: string) => {
  const trimmed = s.trim().replace(/^https?:\/\//, "");
  return trimmed.includes(".") && trimmed.length > 4 && !trimmed.includes(" ");
};

const displayUrlOf = (url: string) => url.trim().replace(/^https?:\/\//, "").replace(/\/$/, "");

const linkButton = "font-mono text-[11px] text-muted underline transition-colors hover:text-ink";

export function Intake({
  clientId,
  clientName,
  profile,
  onApproved,
  children,
}: {
  clientId: string;
  clientName: string;
  profile: SetupProfile;
  onApproved: (profile: SetupProfile, firstApproval: boolean) => void;
  /** Post-approval sections (Campaign, Brand Voice, Strategy Lens), rendered under the review. */
  children?: ReactNode;
}) {
  const router = useRouter();
  const [step, setStep] = useState<Step>(profile.approved ? 3 : 0);
  const [url, setUrl] = useState(profile.website_url ?? "");
  const [answers, setAnswers] = useState<IntakeAnswers>(profile.answers);
  const [qIndex, setQIndex] = useState(0);
  const [scan, setScan] = useState<BrandProfile | null>(null);
  const [scanError, setScanError] = useState<string | null>(null);
  const [revealed, setRevealed] = useState(0); // rows listed while reading
  const [aiPrefilled, setAiPrefilled] = useState<Set<TextQuestionId>>(new Set());
  const [coaching, setCoaching] = useState<{ value: string; note: string } | null>(null);
  const [checking, setChecking] = useState(false);
  const [confirmStartOver, setConfirmStartOver] = useState(false);
  const [approving, setApproving] = useState(false);
  const [approveError, setApproveError] = useState<string | null>(null);
  const scanAbort = useRef<AbortController | null>(null);
  const checkAbort = useRef<AbortController | null>(null);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(
    () => () => {
      scanAbort.current?.abort();
      checkAbort.current?.abort();
      timers.current.forEach(clearTimeout);
    },
    []
  );

  const displayUrl = displayUrlOf(url) || clientName;
  const leave = () => router.push("/welcome");

  /* ------------------------------------------------------------- scan */
  const startScan = async () => {
    if (!isLikelyUrl(url)) return;
    scanAbort.current?.abort();
    const controller = new AbortController();
    scanAbort.current = controller;
    timers.current.forEach(clearTimeout);
    setStep(1);
    setScan(null);
    setScanError(null);
    setRevealed(0);
    // List what is being looked for, one row at a time — pending, never ticked.
    timers.current = SCAN_ROWS.map((_, i) => setTimeout(() => setRevealed((n) => Math.max(n, i + 1)), 250 + i * 450));
    try {
      const result = await setupApi.scanWebsite(url.trim(), controller.signal);
      if (controller.signal.aborted) return;
      setRevealed(SCAN_ROWS.length);
      setScan(result);
      // Only fill blanks: a human's earlier answer beats the scan's guess.
      // Tone is never prefilled — the human picks it.
      const prefilled = new Set<TextQuestionId>();
      const next = { ...answers };
      const audience = scanValue(result, "target_audience");
      const diff = scanValue(result, "competitor_differentiation");
      if (audience && !answers.audience.trim()) {
        next.audience = audience;
        prefilled.add("audience");
      }
      if (diff && !answers.differentiator.trim()) {
        next.differentiator = diff;
        prefilled.add("differentiator");
      }
      setAnswers(next);
      setAiPrefilled(prefilled);
    } catch (e) {
      if (controller.signal.aborted) return;
      setScanError(e instanceof Error && e.message ? e.message : "Couldn't complete that scan.");
    } finally {
      if (scanAbort.current === controller) scanAbort.current = null;
    }
  };

  const cancelScan = () => {
    scanAbort.current?.abort();
    timers.current.forEach(clearTimeout);
    setScanError(null);
    setStep(0);
  };

  /* --------------------------------------------------------- questions */
  const commitAnswer = (id: keyof IntakeAnswers, value: string) => {
    setAnswers((prev) => ({ ...prev, [id]: value }));
    setCoaching(null);
    setChecking(false);
    if (qIndex < QUESTIONS.length - 1) setQIndex(qIndex + 1);
    else setStep(3);
  };

  const answerCurrent = async (value: string) => {
    if (checking) return;
    const q = QUESTIONS[qIndex];
    setCoaching(null);
    if (q.options) {
      commitAnswer(q.id, value); // fixed choice — inherently specific, no coaching
      return;
    }
    const controller = new AbortController();
    checkAbort.current = controller;
    setChecking(true);
    let result: AnswerCoaching | null = null;
    try {
      result = await setupApi.evaluateAnswer(clientId, q.id as TextQuestionId, value, controller.signal);
    } catch {
      result = null; // never block progress on a failed check — the human has final say
    }
    if (controller.signal.aborted) return;
    setChecking(false);
    if (result?.available && result.is_thin && result.coaching_note) setCoaching({ value, note: result.coaching_note });
    else commitAnswer(q.id, value);
  };

  const goBack = () => {
    checkAbort.current?.abort();
    setChecking(false);
    setCoaching(null);
    if (qIndex > 0) setQIndex(qIndex - 1);
    else setStep(0);
  };

  /* ----------------------------------------------------------- approve */
  const complete = Boolean(answers.audience.trim() && answers.differentiator.trim() && answers.tone);
  const approve = async () => {
    setApproving(true);
    setApproveError(null);
    try {
      const saved = await setupApi.approveProfile(clientId, {
        url: url.trim() || null,
        audience: answers.audience.trim(),
        differentiator: answers.differentiator.trim(),
        tone: answers.tone,
      });
      const first = !profile.approved;
      trackFeature("brand-profile-approved");
      toast.success(`Brand profile approved for ${displayUrl}`);
      onApproved(saved, first);
    } catch (e) {
      setApproveError(e instanceof Error ? e.message : "Couldn't approve the profile.");
    } finally {
      setApproving(false);
    }
  };

  const startOver = () => {
    setStep(0);
    setUrl("");
    setAnswers({ audience: "", differentiator: "", tone: "" });
    setScan(null);
    setAiPrefilled(new Set());
    setQIndex(0);
    setConfirmStartOver(false);
  };

  const q = QUESTIONS[qIndex];

  return (
    <div className="space-y-6">
      {step === 0 && (
        <Panel dashed className="p-6 motion-safe:animate-screen-in sm:p-8">
          <Eyebrow>{profile.approved ? "Re-scan the website" : "New brand profile"}</Eyebrow>
          <h2 className="mt-3 font-mono text-xl leading-snug text-ink sm:text-2xl">
            Drop {clientName}&apos;s link.
            <br />
            <span className="text-muted">
              We&apos;ll read it before we ask you anything.
              <span aria-hidden className="ml-1 inline-block h-5 w-[9px] animate-pulse-dot bg-accent align-text-bottom" />
            </span>
          </h2>
          <div className="mt-6 flex items-center gap-2 rounded-lg border border-line bg-panel px-3 py-3 backdrop-blur-xl transition-all duration-200 focus-within:border-accent focus-within:ring-[3px] focus-within:ring-accent/20">
            <Search className="h-4 w-4 shrink-0 text-muted" />
            <input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && void startScan()}
              placeholder="https://yourclient.com"
              aria-label="Client website"
              className="w-full bg-transparent font-mono text-sm text-ink outline-none placeholder:text-slate-400"
            />
          </div>
          <div className="mt-5 flex flex-wrap items-center gap-3">
            <Button onClick={() => void startScan()} disabled={!isLikelyUrl(url)} className={cn(isLikelyUrl(url) && "animate-breathe")}>
              Start scan <ArrowRight className="h-3.5 w-3.5" />
            </Button>
            {url.trim() && !isLikelyUrl(url) && (
              <span className="font-mono text-[11px] text-red-600">Enter a real domain, e.g. myclient.com</span>
            )}
          </div>
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            <p className="font-mono text-[11px] text-muted">No login page? No problem — public marketing pages work best.</p>
            <div className="flex items-center gap-4">
              <button
                type="button"
                onClick={() => {
                  setQIndex(0);
                  setStep(2);
                }}
                className={linkButton}
              >
                Skip the scan
              </button>
              {profile.approved ? (
                <button type="button" onClick={() => setStep(3)} className={linkButton}>
                  ← Back to profile
                </button>
              ) : (
                <button type="button" onClick={leave} className={linkButton}>
                  Cancel
                </button>
              )}
            </div>
          </div>
        </Panel>
      )}

      {step === 1 && (
        <Panel className="overflow-hidden motion-safe:animate-screen-in">
          <div className="flex items-center gap-2 border-b border-line px-4 py-2.5">
            <div className="flex gap-1.5" aria-hidden>
              {[0, 1, 2].map((i) => (
                <span key={i} className="h-2.5 w-2.5 rounded-full bg-slate-400/40" />
              ))}
            </div>
            <div className="ml-2 flex-1 truncate font-mono text-[11px] text-muted">{displayUrl}</div>
            <Scan className={cn("h-3.5 w-3.5 text-accent-text", !scan && !scanError && "animate-pulse-dot")} />
          </div>
          {!scan && !scanError && (
            <div className="relative h-40 overflow-hidden border-b border-line" aria-hidden>
              <div className="absolute inset-x-0 h-16 animate-scanline bg-gradient-to-b from-transparent via-accent/30 to-transparent" />
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 font-mono text-[11px] text-muted">
                <FileText className="mb-1 h-5 w-5 text-slate-300" /> reading {displayUrl}
              </div>
            </div>
          )}
          <ul className="space-y-2 px-4 py-4" aria-live="polite">
            {SCAN_ROWS.map((row, i) => {
              const listed = scan !== null || i < revealed;
              const value = scan ? scanValue(scan, row.key) : "";
              return (
                <li
                  key={row.key}
                  style={scan ? { animationDelay: `${i * 0.12}s` } : undefined}
                  className={cn(
                    "flex items-start gap-2 font-mono text-xs transition-all duration-300",
                    listed ? "translate-x-0 opacity-100" : "-translate-x-1.5 opacity-0",
                    scan && "motion-safe:animate-screen-in"
                  )}
                >
                  {!scan ? (
                    scanError ? (
                      <Minus className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-400" />
                    ) : (
                      <Loader2 className="mt-0.5 h-3.5 w-3.5 shrink-0 animate-spin text-slate-400" />
                    )
                  ) : value ? (
                    <CheckCircle2
                      style={{ animationDelay: `${i * 0.12}s` }}
                      className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent-text motion-safe:animate-pop-in"
                    />
                  ) : (
                    <Minus className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-400" />
                  )}
                  {!scan ? (
                    <span className="text-muted">{row.looking}</span>
                  ) : (
                    <span className="min-w-0">
                      <span className="text-muted">{row.found}: </span>
                      {value ? (
                        <span className="text-ink">{value}</span>
                      ) : (
                        <span className="text-muted">not found on the page</span>
                      )}
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
          {scanError ? (
            <div className="space-y-3 px-4 pb-4">
              <ErrorBanner message={`${scanError} Try again, check the URL, or answer the questions yourself.`} onRetry={() => void startScan()} />
              <div className="flex justify-end gap-4">
                <button type="button" onClick={() => { setQIndex(0); setStep(2); }} className={linkButton}>
                  Answer without the scan
                </button>
                <button type="button" onClick={cancelScan} className={linkButton}>
                  ← Back
                </button>
              </div>
            </div>
          ) : scan ? (
            <div className="flex flex-wrap items-center justify-between gap-3 px-4 pb-4">
              <span className="font-mono text-[10.5px] text-muted">Read from {displayUrl} — you confirm everything next.</span>
              <div className="flex items-center gap-4">
                <button type="button" onClick={cancelScan} className={linkButton}>
                  ← Back
                </button>
                <Button
                  size="sm"
                  onClick={() => {
                    setQIndex(0);
                    setStep(2);
                  }}
                >
                  Continue <ArrowRight className="h-3 w-3" />
                </Button>
              </div>
            </div>
          ) : (
            <div className="flex justify-end px-4 pb-4">
              <button type="button" onClick={cancelScan} className={linkButton}>
                Cancel
              </button>
            </div>
          )}
        </Panel>
      )}

      {step === 2 && (
        <Panel dashed key={`q-${qIndex}`} className="p-6 motion-safe:animate-screen-in sm:p-8">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <Eyebrow>
              Question {qIndex + 1} of {QUESTIONS.length} — only you can confirm this
            </Eyebrow>
            <div className="flex items-center gap-4">
              <button type="button" onClick={goBack} className={linkButton}>
                ← Back
              </button>
              <button type="button" onClick={profile.approved ? () => setStep(3) : leave} className={linkButton}>
                Cancel
              </button>
            </div>
          </div>
          <h2 className="mt-3 font-mono text-lg text-ink sm:text-xl">{q.label}</h2>
          {q.options ? (
            <div className="mt-6 grid gap-2 sm:grid-cols-2">
              {q.options.map((opt, i) => (
                <button
                  key={opt}
                  type="button"
                  onClick={() => void answerCurrent(opt)}
                  style={{ animationDelay: `${i * 0.06}s` }}
                  className={cn(
                    "rounded-xl border bg-panel px-4 py-3 text-left font-mono text-[13px] text-ink backdrop-blur-xl transition-all duration-200 hover:-translate-y-0.5 hover:border-accent hover:bg-accent/10 motion-safe:animate-screen-in",
                    answers.tone === opt ? "border-accent" : "border-line"
                  )}
                >
                  {opt}
                  {answers.tone === opt && <span className="ml-2 font-mono text-[10px] text-accent-text">current</span>}
                </button>
              ))}
            </div>
          ) : (
            <>
              <QuestionInput
                key={q.id}
                placeholder={q.placeholder ?? ""}
                initialValue={coaching?.value ?? answers[q.id]}
                hint={aiPrefilled.has(q.id as TextQuestionId) ? "Pre-filled from the scan — edit if it's off" : null}
                disabled={checking}
                onSubmit={(v) => void answerCurrent(v)}
              />
              {checking && (
                <div className="mt-3 flex items-center gap-2 font-mono text-[11px] text-muted">
                  <Loader2 className="h-3 w-3 animate-spin" /> Checking specificity…
                </div>
              )}
              {coaching && (
                <div className="mt-3 rounded-lg border border-accent/35 bg-accent/5 p-4 motion-safe:animate-screen-in">
                  <div className="flex items-start gap-2">
                    <Lightbulb className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent-text" />
                    <p className="text-[12.5px] leading-normal text-slate-600">{coaching.note}</p>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <Button size="sm" variant="secondary" onClick={() => setCoaching(null)}>
                      Let me revise
                    </Button>
                    <Button size="sm" onClick={() => commitAnswer(q.id, coaching.value)}>
                      Keep as-is, continue
                    </Button>
                  </div>
                </div>
              )}
            </>
          )}
        </Panel>
      )}

      {step === 3 && (
        <Panel className="motion-safe:animate-screen-in">
          <div className="flex items-center justify-between border-b border-dashed border-line px-6 py-4">
            <Eyebrow>{profile.approved ? "Brand profile" : "Profile draft — ready for review"}</Eyebrow>
            <span className="font-mono text-[11px] text-accent-text">{profile.approved ? "approved" : "draft"}</span>
          </div>
          <div className="px-6 py-6">
            <h2 className="font-mono text-xl text-ink sm:text-2xl">{displayUrl}</h2>
            <p className="mt-1 font-mono text-xs text-muted">
              {scan ? `From the site scan + ${QUESTIONS.length} clarifying answers` : `${QUESTIONS.length} clarifying answers`}
            </p>
            <div className="mt-6 grid gap-4">
              {(
                [
                  ["Audience", answers.audience],
                  ["Differentiator", answers.differentiator],
                  ["Voice", answers.tone],
                  ...(scan && scanValue(scan, "content_pillars") ? [["Topics from the scan", scanValue(scan, "content_pillars")]] : []),
                ] as [string, string][]
              ).map(([label, value], i) => (
                <div
                  key={label}
                  style={{ animationDelay: `${i * 0.1}s` }}
                  className="border-l-2 border-line pl-4 motion-safe:animate-screen-in"
                >
                  <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-muted">{label}</div>
                  <div className="mt-1 text-sm text-ink">{value || "—"}</div>
                </div>
              ))}
            </div>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Button onClick={() => void approve()} disabled={!complete || approving}>
                {approving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                Approve profile <ArrowRight className="h-3.5 w-3.5" />
              </Button>
              <Button variant="secondary" onClick={() => setConfirmStartOver(true)} disabled={approving}>
                Start over
              </Button>
              <button
                type="button"
                onClick={() => {
                  setQIndex(0);
                  setStep(2);
                }}
                className={linkButton}
              >
                ← Back to edit answers
              </button>
              {!complete && <span className="font-mono text-[11px] text-muted">Answer all three questions first.</span>}
            </div>
            {approveError && <ErrorBanner message={approveError} onRetry={() => void approve()} />}
            <ConfirmDialog
              open={confirmStartOver}
              title={profile.approved ? "Start over? This client already has an approved profile." : "Start over?"}
              message={
                profile.approved
                  ? "This clears the URL and all answers on this screen and re-scans from scratch. The approved profile stays untouched until you hit Approve profile again — but you'll lose these unsaved edits."
                  : "This clears the URL and all answers you've entered so far — you'll start the scan from scratch."
              }
              confirmLabel="Start over"
              onConfirm={startOver}
              onCancel={() => setConfirmStartOver(false)}
            />
            {profile.approved && children && (
              <div className="mt-8 space-y-8 border-t border-dashed border-line pt-6">{children}</div>
            )}
          </div>
        </Panel>
      )}
    </div>
  );
}

function QuestionInput({
  placeholder,
  initialValue,
  hint,
  disabled,
  onSubmit,
}: {
  placeholder: string;
  initialValue: string;
  hint: string | null;
  disabled: boolean;
  onSubmit: (value: string) => void;
}) {
  const [val, setVal] = useState(initialValue);
  const ready = val.trim().length > 0 && !disabled;
  return (
    <div className="mt-6">
      {hint && (
        <div className="mb-2 flex items-center gap-1.5 font-mono text-[10.5px] text-accent-text">
          <Sparkle className="h-[11px] w-[11px]" /> {hint}
        </div>
      )}
      <div className="flex items-center gap-2 rounded-lg border border-line bg-panel px-3 py-3 backdrop-blur-xl transition-all duration-200 focus-within:border-accent focus-within:ring-[3px] focus-within:ring-accent/20">
        <input
          value={val}
          onChange={(e) => setVal(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && ready && onSubmit(val.trim())}
          placeholder={placeholder}
          aria-label={placeholder}
          maxLength={600}
          autoFocus
          className="w-full bg-transparent font-mono text-sm text-ink outline-none placeholder:text-slate-400"
        />
        <Button size="sm" onClick={() => ready && onSubmit(val.trim())} disabled={!ready} className="shrink-0">
          Next
        </Button>
      </div>
    </div>
  );
}
