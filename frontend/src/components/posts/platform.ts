/*
 * Platform names and colours shared by the Queue and the Calendar. Only hues
 * that tailwind.config.ts remaps for dark mode are used (no pink/indigo-as-blue),
 * so the chips stay legible on the navy panels.
 */

export const QUEUE_PLATFORMS = [
  { id: "linkedin", label: "LinkedIn" },
  { id: "twitter", label: "X" },
  { id: "facebook", label: "Facebook" },
  { id: "instagram", label: "Instagram" },
  { id: "tiktok", label: "TikTok" },
] as const;

// Channel display names live in one place for the whole app (CF-19) — this used
// to keep a second map that named X "X" and Google Ads "Google" while other
// screens printed the raw slug. Re-exported so the Queue and Calendar imports
// keep working.
export { platformLabel } from "@/lib/platforms";

type Tone = { dot: string; chip: string; pill: string };

const TONES: Record<string, Tone> = {
  linkedin: {
    dot: "bg-sky-500",
    chip: "border-sky-200 bg-sky-50 text-sky-700",
    pill: "border-l-sky-500 bg-sky-100 text-sky-800 hover:bg-sky-200",
  },
  twitter: {
    dot: "bg-slate-700",
    chip: "border-slate-300 bg-slate-100 text-slate-700",
    pill: "border-l-slate-600 bg-slate-200/70 text-slate-800 hover:bg-slate-200",
  },
  facebook: {
    dot: "bg-blue-500",
    chip: "border-blue-200 bg-blue-50 text-blue-700",
    pill: "border-l-blue-500 bg-blue-100 text-blue-800 hover:bg-blue-200",
  },
  instagram: {
    dot: "bg-rose-500",
    chip: "border-rose-200 bg-rose-50 text-rose-700",
    pill: "border-l-rose-500 bg-rose-100 text-rose-800 hover:bg-rose-200",
  },
  tiktok: {
    dot: "bg-teal-500",
    chip: "border-teal-200 bg-teal-50 text-teal-700",
    pill: "border-l-teal-500 bg-teal-100 text-teal-800 hover:bg-teal-200",
  },
};
TONES.x = TONES.twitter;
TONES.meta = TONES.facebook;

const OTHER: Tone = {
  dot: "bg-slate-400",
  chip: "border-slate-200 bg-slate-50 text-slate-600",
  pill: "border-l-slate-400 bg-slate-100 text-slate-700 hover:bg-slate-200",
};

export function platformTone(platform: string | null | undefined): Tone {
  return TONES[(platform ?? "").toLowerCase()] ?? OTHER;
}
