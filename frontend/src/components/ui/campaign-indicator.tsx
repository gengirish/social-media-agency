"use client";

import Link from "next/link";
import { Megaphone } from "lucide-react";
import { useActiveClient } from "@/lib/active-client";

/**
 * Cadence's CampaignIndicator: a small persistent reminder, above any
 * generate control, that the active client's campaign focus is shaping the
 * output. Without it the focus would be invisible magic — set once, days ago,
 * on another screen. Renders nothing when no focus is set.
 */
export function CampaignIndicator({ editable = true }: { editable?: boolean }) {
  const { active } = useActiveClient();
  const desc = active?.campaign_focus;
  if (!desc) return null;
  return (
    <div className="mb-2 flex items-center gap-1.5 font-mono text-[10.5px] text-accent-text">
      <Megaphone aria-hidden className="h-[11px] w-[11px] shrink-0" />
      <span className="truncate">Campaign active: &ldquo;{desc}&rdquo;</span>
      {editable && (
        <Link href="/setup/profile#campaign" className="shrink-0 underline">
          Edit
        </Link>
      )}
    </div>
  );
}
