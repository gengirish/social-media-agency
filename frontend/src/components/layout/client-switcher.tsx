"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, ChevronDown, Plus, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { clientLabel, useActiveClient } from "@/lib/active-client";
import { useSession } from "@/lib/session";
import type { ClientOverview } from "@/lib/api-foundation";
import { ConfirmDialog } from "@/components/ui/feedback";
import { cn } from "@/lib/utils";

/**
 * Cadence's product switcher, mapped onto clients: the active client scopes
 * every Create / Posts / Insights screen. Status lines are the client's real
 * counts from /clients/overview — nothing is estimated.
 */
export function ClientSwitcher() {
  const { clients, active, activeId, setActiveId, loading, refresh } = useActiveClient();
  const { isPersonal } = useSession();
  const [open, setOpen] = useState(false);
  const [confirmArchive, setConfirmArchive] = useState<ClientOverview | null>(null);
  const [archiving, setArchiving] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    const onClick = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onClick);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onClick);
    };
  }, [open]);

  const archive = async () => {
    if (!confirmArchive) return;
    setArchiving(true);
    try {
      await api.archiveClient(confirmArchive.id);
      toast.success(`${clientLabel(confirmArchive)} archived — restore it from Setup › Clients.`);
      setConfirmArchive(null);
      await refresh();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not archive this client");
    } finally {
      setArchiving(false);
    }
  };

  const many = clients.length > 1;
  const name = loading ? "Loading…" : clientLabel(active);

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`Switch client, currently ${name}`}
        className={cn(
          "flex max-w-[180px] items-center gap-1.5 overflow-hidden rounded-md border px-2.5 py-1 font-mono text-[11.5px] transition-colors",
          open
            ? "border-accent bg-panel"
            : many
              ? "border-accent/30 bg-accent/5 text-accent-text"
              : "border-line text-muted"
        )}
      >
        <span className="truncate">{name}</span>
        <ChevronDown className={cn("h-3 w-3 shrink-0 transition-transform duration-200", open && "rotate-180")} />
      </button>

      {open && (
        <div className="absolute left-0 top-full z-50 mt-1.5 w-[300px] animate-screen-in overflow-hidden rounded-xl border border-line bg-panel shadow-soft backdrop-blur-xl">
          <div className="border-b border-line px-3 pb-1.5 pt-2 text-[10.5px] font-medium text-muted">Your clients</div>
          <div role="listbox" aria-label="Your clients" className="max-h-72 overflow-y-auto">
            {clients.length === 0 && !loading && (
              <p className="px-3 py-3 text-xs text-muted">No clients yet. Add one to start.</p>
            )}
            {clients.map((c) => {
              const isActive = c.id === activeId;
              const label = clientLabel(c);
              return (
                <div
                  key={c.id}
                  role="option"
                  aria-selected={isActive}
                  tabIndex={0}
                  onClick={() => {
                    setActiveId(c.id);
                    setOpen(false);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      setActiveId(c.id);
                      setOpen(false);
                    }
                  }}
                  className={cn(
                    "press-scale flex w-full cursor-pointer items-start gap-2.5 border-b border-line px-3 py-2.5 text-left",
                    isActive && "bg-accent/5"
                  )}
                >
                  <span
                    className={cn(
                      "mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md border",
                      isActive ? "border-accent bg-accent/10 text-accent-text" : "border-line text-muted"
                    )}
                  >
                    {isActive ? <CheckCircle2 className="h-3 w-3" /> : <span className="font-mono text-[10px]">{label[0]?.toUpperCase()}</span>}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center justify-between gap-1">
                      <span className={cn("truncate font-mono text-xs", isActive ? "text-accent-text" : "text-ink")}>{label}</span>
                      {many && (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setOpen(false);
                            setConfirmArchive(c);
                          }}
                          aria-label={`Archive ${label}`}
                          className="shrink-0 text-muted hover:text-red-600"
                        >
                          <Trash2 className="h-[11px] w-[11px]" />
                        </button>
                      )}
                    </span>
                    <ClientStatusLine c={c} />
                  </span>
                </div>
              );
            })}
          </div>
          {/* A personal account has exactly one brand, created at signup. Adding a
              second is what makes it an agency, and that is a plan change rather
              than a link in a dropdown — so no add affordance until it is one. */}
          {!isPersonal && (
            <Link
              href="/clients?new=1"
              onClick={() => setOpen(false)}
              className="flex w-full items-center gap-1.5 px-3 py-2.5 text-[12.5px] font-medium text-accent-text"
            >
              <Plus className="h-3.5 w-3.5" /> Add another client
            </Link>
          )}
        </div>
      )}

      <ConfirmDialog
        open={confirmArchive !== null}
        title="Archive this client?"
        message="It leaves the switcher and every picker. Its posts, campaigns and profile are kept, and you can restore it from Setup › Clients."
        confirmLabel="Archive client"
        busy={archiving}
        onConfirm={archive}
        onCancel={() => setConfirmArchive(null)}
      />
    </div>
  );
}

function ClientStatusLine({ c }: { c: ClientOverview }) {
  return (
    <span className="mt-1 flex flex-wrap items-center gap-2 text-[10px]">
      {!c.has_brand_profile && <span className="text-red-600">Profile needed</span>}
      {c.has_brand_profile && c.connected_accounts === 0 && <span className="text-accent-text">No accounts connected</span>}
      {c.connected_accounts > 0 && (
        <span className="text-muted">
          {c.connected_accounts} channel{c.connected_accounts === 1 ? "" : "s"}
        </span>
      )}
      {c.pending > 0 && <span className="text-accent-text">{c.pending} to review</span>}
      {c.published > 0 && <span className="text-emerald-600">{c.published} published</span>}
      {c.has_brand_profile && c.connected_accounts > 0 && c.pending === 0 && c.published === 0 && (
        <span className="text-muted">Ready to generate</span>
      )}
    </span>
  );
}
