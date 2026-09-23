"use client";

import { useEffect, useState } from "react";
import { format } from "date-fns";
import { CheckCircle2, Loader2 } from "lucide-react";
import { PLATFORM_LIMITS } from "@/lib/api-posts";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { PostDialog } from "./dialog";
import { platformLabel, platformTone } from "./platform";

/**
 * Cadence's AddPostModal: a hand-written post pinned to a calendar day. It is
 * created Pending — never scheduled — so it passes moderation at approval like
 * every other post (the exact bug Cadence documents fixing).
 */
export function AddPostModal({
  day,
  platforms,
  connected,
  busy,
  onAdd,
  onClose,
}: {
  day: Date | null;
  platforms: string[];
  connected: string[];
  busy: boolean;
  onAdd: (data: { platform: string; body: string }) => void;
  onClose: () => void;
}) {
  const [platform, setPlatform] = useState("");
  const [body, setBody] = useState("");

  useEffect(() => {
    if (day) {
      setPlatform(connected[0] ?? "");
      setBody("");
    }
  }, [day, connected]);

  const limit = PLATFORM_LIMITS[platform] ?? null;
  const over = limit !== null && body.length > limit;
  const ok = Boolean(body.trim()) && connected.includes(platform) && !over;

  return (
    <PostDialog
      open={day !== null}
      onOpenChange={(o) => !o && onClose()}
      busy={busy}
      title={day ? `Add your own post — ${format(day, "EEE d")}` : "Add your own post"}
      footer={
        <div className="w-full">
          <Button className="w-full" disabled={!ok || busy} onClick={() => onAdd({ platform, body: body.trim() })}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
            Add to calendar
          </Button>
          {connected.length === 0 && (
            <p className="mt-2 text-center font-mono text-[10.5px] text-muted">
              Connect an account in Setup before adding posts.
            </p>
          )}
        </div>
      }
    >
      <div className="mb-1.5 text-[11px] font-medium text-muted">Platform</div>
      <div className="flex gap-2" role="radiogroup" aria-label="Platform">
        {platforms.map((id) => {
          const isConnected = connected.includes(id);
          const active = platform === id;
          return (
            <button
              key={id}
              type="button"
              role="radio"
              aria-checked={active}
              disabled={!isConnected}
              title={isConnected ? platformLabel(id) : `${platformLabel(id)} — connect this in Setup first`}
              onClick={() => setPlatform(id)}
              className={cn(
                "flex h-9 flex-1 items-center justify-center gap-1.5 rounded-md border font-mono text-[10.5px] transition-colors",
                active ? "border-accent bg-accent/10 text-ink" : "border-line text-muted",
                !isConnected && "cursor-not-allowed opacity-35"
              )}
            >
              <span aria-hidden className={cn("h-2 w-2 rounded-full", platformTone(id).dot)} />
              <span className="hidden sm:inline">{platformLabel(id)}</span>
            </button>
          );
        })}
      </div>
      <div className="mb-1.5 mt-4 text-[11px] font-medium text-muted">Your post</div>
      <textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        rows={4}
        placeholder="Write exactly what you want to go out…"
        className={cn(
          "w-full resize-none rounded-lg border bg-panel px-3 py-2.5 text-[13px] text-ink outline-none transition-[border-color,box-shadow] duration-200 placeholder:text-slate-400 focus:shadow-[0_0_0_3px_rgb(var(--c-accent)/0.12)]",
          over ? "border-red-400" : "border-line focus:border-accent"
        )}
      />
      <div className="mt-1 flex justify-between font-mono text-[10px] text-muted">
        <span>Lands as Pending — approve it in the Queue, then schedule it.</span>
        <span className={cn(over && "text-red-600")}>
          {body.length}
          {limit ? ` / ${limit}` : ""}
        </span>
      </div>
    </PostDialog>
  );
}
