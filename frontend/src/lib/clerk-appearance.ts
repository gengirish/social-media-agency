import type { Theme } from "@/lib/theme";

/*
 * Clerk's widget renders in its own styles, so the root layout's appearance
 * (amber primary only) leaves a white card on the dark canvas. Clerk resolves
 * colors in JS, so CSS variables are not reliable here — the palette is passed
 * as literal hex per theme. Both the current (colorForeground, colorInput…)
 * and the older (colorText, colorInputBackground…) variable names are set, so
 * this holds on either side of Clerk's rename.
 */
const PALETTE = {
  light: {
    colorBackground: "#FFFFFF",
    colorForeground: "#0E1B2A",
    colorText: "#0E1B2A",
    colorMutedForeground: "#475A6D",
    colorTextSecondary: "#475A6D",
    colorInput: "#F4F6F9",
    colorInputBackground: "#F4F6F9",
    colorInputForeground: "#0E1B2A",
    colorInputText: "#0E1B2A",
    colorNeutral: "#0E1B2A",
    colorBorder: "#DDE4EC",
  },
  dark: {
    colorBackground: "#122030",
    colorForeground: "#EEF3F9",
    colorText: "#EEF3F9",
    colorMutedForeground: "#93A9BF",
    colorTextSecondary: "#93A9BF",
    colorInput: "#0E1B2A",
    colorInputBackground: "#0E1B2A",
    colorInputForeground: "#EEF3F9",
    colorInputText: "#EEF3F9",
    colorNeutral: "#EEF3F9",
    colorBorder: "#2E465E",
  },
} as const;

/** Clerk `appearance.variables` for the current theme — used by every Clerk widget we render. */
export function clerkVariables(theme: Theme) {
  return {
    ...PALETTE[theme],
    colorPrimary: "#F2C14E",
    colorPrimaryForeground: "#1A1406",
    colorTextOnPrimaryBackground: "#1A1406",
    colorRing: "#F2C14E",
    fontFamily: "var(--font-sans), Inter, system-ui, sans-serif",
    borderRadius: "0.6rem",
  };
}
