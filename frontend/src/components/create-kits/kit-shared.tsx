"use client";

/*
 * Shared pieces of Create › Email and Create › Launch (Cadence's EmailScreen
 * and LaunchScreen): the list-of-drafts store backed by /assets, the generate
 * lifecycle (cancel, quota, brand-profile gate, error with retry), and the
 * card chrome both screens use.
 */

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { CheckCircle2, Loader2, Trash2, UserPlus, Wand2 } from "lucide-react";
import { toast } from "sonner";
import { api, apiErrorStatus, isGenerationQuotaError } from "@/lib/api";
import { foundationApi, type AssetKind, type CreativeAsset } from "@/lib/api-foundation";
import { copyText, isBrandProfileRequired } from "@/lib/api-create-kits";
import { useActiveClient } from "@/lib/active-client";
import { Button, buttonVariants } from "@/components/ui/button";
import { Panel } from "@/components/ui/panel";
import { QuotaHint } from "@/components/ui/quota-hint";
import { ErrorBanner, undoToast } from "@/components/ui/feedback";
import { EmptyState, LoadingState } from "@/components/ui/empty-state";
import { cn } from "@/lib/utils";

/** Cadence caps every list at 100 items; the asset store pages at 200. */
const LIST_LIMIT = 100;

// ---------------------------------------------------------------------------
// Quota
// ---------------------------------------------------------------------------
export function useGenerationQuota() {
  const [used, setUsed] = useState<number | null>(null);
  const [limit, setLimit] = useState<number | null>(null);
  const [blocked, setBlocked] = useState(false);

  const reload = useCallback(() => {
    api
      .getSubscription()
      .then((s) => {
        setUsed(s.generations_used ?? null);
        setLimit(s.generations_limit ?? null);
      })
      // Unknown quota renders nothing — never a guessed number.
      .catch(() => {
        setUsed(null);
        setLimit(null);
      });
  }, []);

  useEffect(() => reload(), [reload]);

  const exhausted = blocked || (used != null && limit != null && used >= limit);
  const markExhausted = useCallback(() => setBlocked(true), []);
  return { used, limit, exhausted, reload, markExhausted };
}

// ---------------------------------------------------------------------------
// Draft list backed by the asset store
// ---------------------------------------------------------------------------
export function useKitAssets<P>(clientId: string | null, kind: AssetKind) {
  const [items, setItems] = useState<CreativeAsset<P>[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);

  const reload = useCallback(async () => {
    if (!clientId) {
      setItems([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const res = await foundationApi.listAssets<P>({ clientId, kinds: [kind], limit: LIST_LIMIT });
      setItems(res.items);
      setLoadError(false);
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, [clientId, kind]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const prepend = useCallback((item: CreativeAsset<P>) => {
    setItems((prev) => [item, ...prev.filter((p) => p.id !== item.id)].slice(0, LIST_LIMIT));
  }, []);

  /** Cadence's soft delete: gone at once, 8 s to undo, server delete when the window closes. */
  const removeWithUndo = useCallback(
    (item: CreativeAsset<P>, message: string) => {
      let index = -1;
      setItems((prev) => {
        index = prev.findIndex((p) => p.id === item.id);
        return prev.filter((p) => p.id !== item.id);
      });
      const restore = () =>
        setItems((prev) => {
          if (prev.some((p) => p.id === item.id)) return prev;
          const next = [...prev];
          next.splice(Math.max(0, Math.min(index, next.length)), 0, item);
          return next;
        });
      undoToast(message, restore, () => {
        foundationApi.deleteAsset(item.id).catch(() => {
          restore();
          toast.error("Couldn't delete that draft — it's back in the list.");
        });
      });
    },
    []
  );

  return { items, loading, loadError, reload, prepend, removeWithUndo };
}

// ---------------------------------------------------------------------------
// Generate lifecycle
// ---------------------------------------------------------------------------
export type GenerateFailure = "quota" | "profile" | "error" | null;

/** `resetKey` (the active client id) clears a stale failure banner on switch. */
export function useGenerator(resetKey?: string | null) {
  const [generating, setGenerating] = useState(false);
  const [failure, setFailure] = useState<GenerateFailure>(null);
  const [message, setMessage] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(() => () => controllerRef.current?.abort(), []);
  useEffect(() => {
    setFailure(null);
    setMessage(null);
  }, [resetKey]);

  const run = useCallback(async <T,>(call: (signal: AbortSignal) => Promise<T>): Promise<T | null> => {
    const controller = new AbortController();
    controllerRef.current = controller;
    setGenerating(true);
    setFailure(null);
    setMessage(null);
    try {
      return await call(controller.signal);
    } catch (err) {
      if (controller.signal.aborted) {
        toast("Generation cancelled");
      } else if (isGenerationQuotaError(err)) {
        setFailure("quota");
      } else if (isBrandProfileRequired(err)) {
        setFailure("profile");
      } else {
        setFailure("error");
        const status = apiErrorStatus(err);
        setMessage(status === 404 ? "That client no longer exists in this workspace." : null);
      }
      return null;
    } finally {
      controllerRef.current = null;
      setGenerating(false);
    }
  }, []);

  const cancel = useCallback(() => controllerRef.current?.abort(), []);
  const clear = useCallback(() => setFailure(null), []);
  return { generating, failure, message, run, cancel, clear };
}

// ---------------------------------------------------------------------------
// Copy
// ---------------------------------------------------------------------------
export function useCopied() {
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const copy = useCallback(async (id: string, text: string) => {
    if (await copyText(text)) {
      setCopiedId(id);
      setTimeout(() => setCopiedId((c) => (c === id ? null : c)), 1800);
    } else {
      toast.error("Couldn't copy — your browser blocked clipboard access.");
    }
  }, []);
  return { copiedId, copy };
}

/** Case-insensitive match over the title and every text value in the payload. */
export function matchesSearch(asset: CreativeAsset<unknown>, q: string): boolean {
  const needle = q.trim().toLowerCase();
  if (!needle) return true;
  return `${asset.title} ${JSON.stringify(asset.payload)}`.toLowerCase().includes(needle);
}

// ---------------------------------------------------------------------------
// UI
// ---------------------------------------------------------------------------

/** Loading / error / no-client states around a Create screen, then the screen itself. */
export function ClientGate({ children }: { children: ReactNode }) {
  const { clients, active, loading, error, refresh } = useActiveClient();
  if (loading) return <LoadingState label="Loading your workspace…" />;
  if (error) {
    return (
      <ErrorBanner message="Couldn't load your clients." onRetry={() => void refresh()} />
    );
  }
  if (clients.length === 0 || !active) {
    return (
      <EmptyState
        icon={UserPlus}
        title="Add a client first"
        description="Everything here is written for one client's brand. Add the first client you manage to get started."
        action={
          <Link href="/clients?new=1" className={buttonVariants()}>
            <UserPlus className="h-3.5 w-3.5" /> Add a client
          </Link>
        }
      />
    );
  }
  return <>{children}</>;
}

export function GenerateButton({
  onClick,
  generating,
  disabled,
  label,
  generatingLabel,
}: {
  onClick: () => void;
  generating: boolean;
  disabled: boolean;
  label: string;
  generatingLabel: string;
}) {
  return (
    <Button onClick={onClick} disabled={generating || disabled} className={cn(!generating && !disabled && "animate-breathe")}>
      {generating ? (
        <>
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> {generatingLabel}
        </>
      ) : (
        <>
          <Wand2 className="h-3.5 w-3.5" /> {label}
        </>
      )}
    </Button>
  );
}

export function CancelLink({ onClick }: { onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} className="font-mono text-[11px] text-muted underline hover:text-ink">
      Cancel
    </button>
  );
}

export function QuotaFor({ quota }: { quota: ReturnType<typeof useGenerationQuota> }) {
  return <QuotaHint used={quota.used} limit={quota.limit} noun="generations left" />;
}

/** The banner under the controls: brand-profile gate, quota, or a failed generation. */
export function GenerateBanner({
  noProfile,
  quotaExhausted,
  failure,
  message,
  onRetry,
  fallback,
  profileMessage,
}: {
  noProfile: boolean;
  quotaExhausted: boolean;
  failure: GenerateFailure;
  message: string | null;
  onRetry: () => void;
  fallback: string;
  profileMessage: string;
}) {
  const router = useRouter();
  if (noProfile || failure === "profile") {
    return <ErrorBanner message={profileMessage} onRetry={() => router.push("/setup/profile")} retryLabel="Go to Setup" />;
  }
  if (quotaExhausted || failure === "quota") {
    return (
      <ErrorBanner
        message="You've used all your generations for this billing period. Upgrade to keep going."
        onRetry={() => router.push("/settings?tab=billing")}
        retryLabel="See plans"
      />
    );
  }
  if (failure === "error") return <ErrorBanner message={message ?? fallback} onRetry={onRetry} />;
  return null;
}

/** Cadence's Block: a mono uppercase label over its content. */
export function Block({ title, children, className }: { title: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className={className}>
      <div className="mb-1 font-mono text-[9.5px] uppercase tracking-[0.09em] text-muted">{title}</div>
      {children}
    </div>
  );
}

export function CopyButton({
  copied,
  onClick,
  icon: Icon,
  label,
}: {
  copied: boolean;
  onClick: () => void;
  icon: typeof Wand2;
  label: string;
}) {
  return (
    <Button size="sm" onClick={onClick}>
      {copied ? (
        <>
          <CheckCircle2 className="h-3 w-3 animate-pop-in" /> Copied
        </>
      ) : (
        <>
          <Icon className="h-3 w-3" /> {label}
        </>
      )}
    </Button>
  );
}

/** Glass card with Cadence's staggered fadeInUp entrance and a delete control. */
export function KitCard({
  index,
  badge,
  title,
  subtitle,
  onDelete,
  deleteLabel,
  children,
}: {
  index: number;
  badge: ReactNode;
  title: ReactNode;
  subtitle?: ReactNode;
  onDelete: () => void;
  deleteLabel: string;
  children?: ReactNode;
}) {
  return (
    <Panel
      className="p-5 motion-safe:animate-screen-in"
      style={{ animationDelay: `${Math.min(index, 12) * 0.06}s` }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          {badge}
          <h3 className="mt-2 text-[15px] font-semibold text-ink">{title}</h3>
          {subtitle && <p className="mt-1 text-xs leading-relaxed text-muted">{subtitle}</p>}
        </div>
        <button
          type="button"
          onClick={onDelete}
          aria-label={deleteLabel}
          className="press-scale shrink-0 text-muted transition-colors hover:text-red-600"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
      {children}
    </Panel>
  );
}

/** The amber mono chip Cadence puts above each launch/community/outreach card. */
export function AccentBadge({ children }: { children: ReactNode }) {
  return (
    <span className="inline-block rounded border border-accent/30 px-2 py-0.5 font-mono text-[9.5px] uppercase tracking-[0.05em] text-accent-text">
      {children}
    </span>
  );
}

export function ListEmpty({ icon: Icon, text }: { icon: typeof Wand2; text: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-slate-300 py-16 text-muted motion-safe:animate-screen-in">
      <Icon className="h-5 w-5" />
      <span className="font-mono text-xs">{text}</span>
    </div>
  );
}
