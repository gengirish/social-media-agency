"use client";

import { Loader2, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PostDialog } from "./dialog";
import { platformLabel } from "./platform";

/** Publish-now goes straight to a live account, so it asks once. */
export function PublishConfirm({
  open,
  platform,
  clientName,
  busy,
  onConfirm,
  onClose,
}: {
  open: boolean;
  platform: string;
  clientName: string | null;
  busy: boolean;
  onConfirm: () => void;
  onClose: () => void;
}) {
  const where = `${clientName ? `${clientName}'s` : "the client's"} live ${platformLabel(platform)} account`;
  return (
    <PostDialog
      open={open}
      onOpenChange={(o) => !o && onClose()}
      busy={busy}
      title="Publish now?"
      description={`This posts immediately to ${where}. It cannot be unpublished from here.`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={onConfirm} disabled={busy}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            Publish now
          </Button>
        </>
      }
    />
  );
}
