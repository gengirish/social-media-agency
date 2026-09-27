import { type AmplifyAngle } from "@/lib/api";

// One channel-naming source for the whole app (CF-19). Amplify used to read its
// labels out of AMPLIFY_PLATFORMS, which named X "Twitter" while the Queue named
// it "X" and the campaign view printed the raw slug.
export { platformLabel } from "@/lib/platforms";

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

