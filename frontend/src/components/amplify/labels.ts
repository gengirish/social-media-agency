import { AMPLIFY_PLATFORMS, type AmplifyAngle } from "@/lib/api";

export const ANGLE_LABELS: Record<AmplifyAngle, string> = {
  hook: "Hook",
  "how-to": "How-to",
  contrarian: "Contrarian",
  story: "Story",
  "data-point": "Data point",
  question: "Question",
  "behind-the-scenes": "Behind the scenes",
  listicle: "Listicle",
};

export function angleLabel(angle: string): string {
  return ANGLE_LABELS[angle as AmplifyAngle] ?? angle;
}

export function platformLabel(platform: string): string {
  return AMPLIFY_PLATFORMS.find((p) => p.id === platform)?.label ?? platform;
}
