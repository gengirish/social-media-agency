"use client";

/*
 * Cadence's shared feedback primitives: ErrorBanner (inline, with retry),
 * ConfirmDialog (destructive confirm), and undoToast (soft-delete window —
 * Cadence prefers undo over confirm-everywhere for reversible actions).
 */

import type { ReactNode } from "react";
import { AlertTriangle, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { PostDialog } from "@/components/posts/dialog";
import { Button } from "@/components/ui/button";

export function ErrorBanner({
  message,
  onRetry,
  retryLabel = "Try again",
}: {
  message: ReactNode;
  onRetry?: () => void;
  retryLabel?: string;
}) {
  return (
    <div
      role="alert"
      aria-live="assertive"
      className="mt-3 flex animate-screen-in items-center justify-between gap-3 rounded-lg border border-red-300 bg-red-50 px-4 py-3"
    >
      <div className="flex items-center gap-2">
        <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-red-600" />
        <span className="font-mono text-xs text-red-700">{message}</span>
      </div>
      {onRetry && (
        <button type="button" onClick={onRetry} className="shrink-0 font-mono text-[11.5px] text-ink underline">
          {retryLabel}
        </button>
      )}
    </div>
  );
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Delete",
  busy,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: ReactNode;
  message: ReactNode;
  confirmLabel?: string;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <PostDialog
      open={open}
      onOpenChange={(o) => !o && onCancel()}
      busy={busy}
      title={
        <span className="flex flex-col gap-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-red-400 text-red-600">
            <Trash2 className="h-4 w-4" />
          </span>
          {title}
        </span>
      }
      description={message}
      footer={
        <>
          <Button variant="secondary" onClick={onCancel} disabled={busy} className="sm:flex-1">
            Cancel
          </Button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className="press-scale rounded-lg bg-red-500 px-4 py-2.5 text-[13px] font-semibold text-white disabled:opacity-60 sm:flex-1"
          >
            {confirmLabel}
          </button>
        </>
      }
    />
  );
}

/**
 * Undo toast with Cadence's 8-second window. The caller performs the action
 * optimistically and passes how to reverse it; `onExpire` runs only when the
 * window closes without an undo (use it to commit a deferred server delete).
 */
export function undoToast(message: string, onUndo: () => void, onExpire?: () => void) {
  let undone = false;
  toast(message, {
    duration: 8000,
    action: {
      label: "Undo",
      onClick: () => {
        undone = true;
        onUndo();
      },
    },
    onAutoClose: () => {
      if (!undone) onExpire?.();
    },
    onDismiss: () => {
      if (!undone) onExpire?.();
    },
  });
}
