import type { Config } from "tailwindcss";
import defaultColors from "tailwindcss/colors";
import plugin from "tailwindcss/plugin";

/*
 * Design tokens — the Cadence palette (dark navy glass, amber accent), in a
 * light and a dark variant. See docs/cadence-port-plan-260921.md.
 *
 * Every color is a CSS variable holding bare "R G B" channels, so Tailwind's
 * opacity modifiers (`bg-white/80`, `from-indigo-50/30`) keep working.
 *
 * The existing pages are written almost entirely in `slate`, `white` and
 * `indigo`. Rather than rewrite 3k lines of classNames, those three palettes
 * are remapped here: `slate` becomes the navy-tinted neutral ramp (inverted in
 * dark mode), `white` becomes the panel surface, and `indigo` becomes the amber
 * accent. The status hues pages use for badges get dark-mode variants the same
 * way. New components should prefer the semantic names (`canvas`, `panel`,
 * `ink`, `muted`, `line`, `accent`, `on-accent`).
 */

type Ramp = Record<number, string>;
const SHADES = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950] as const;

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)) as [number, number, number];
}

function channels(hex: string): string {
  return hexToRgb(hex).join(" ");
}

/** Blend `top` over `base` at opacity `t`, returned as channels. */
function mix(base: string, top: string, t: number): string {
  const a = hexToRgb(base);
  const b = hexToRgb(top);
  return a.map((v, i) => Math.round(v * (1 - t) + b[i] * t)).join(" ");
}

function ramp(values: string[]): Ramp {
  return Object.fromEntries(SHADES.map((s, i) => [s, values[i]]));
}

const AMBER = "#F2C14E";
const PANEL_DARK = "#122030";

const light = {
  canvas: "#F4F6F9",
  white: "#FFFFFF",
  slate: ramp(["#F5F7FA", "#EDF1F5", "#DDE4EC", "#C4CFDB", "#8D9DAF", "#5F7285", "#475A6D", "#334556", "#1F2F3F", "#0E1B2A", "#07111C"]),
  // Deep ochre, not bright amber: legacy buttons pair `bg-indigo-600` with
  // `text-white`, and white on #9A6A0B clears 4.5:1.
  indigo: ramp(["#FDF7E7", "#FAEBC4", "#F3D78E", "#E9BE55", "#D9A232", "#B7831A", "#9A6A0B", "#7F5608", "#654406", "#4A3204", "#2E1F02"]),
  accentText: "#8A5F08",
};

const dark = {
  canvas: "#0A1420",
  white: PANEL_DARK,
  slate: ramp(["#0E1B2A", "#15263A", "#22364B", "#2E465E", "#6A8399", "#7A95AD", "#93A9BF", "#CBD8E5", "#E2EAF3", "#EEF3F9", "#F7FAFD"]),
  indigo: {
    50: mix(PANEL_DARK, AMBER, 0.1),
    100: mix(PANEL_DARK, AMBER, 0.16),
    200: mix(PANEL_DARK, AMBER, 0.28),
    300: mix(PANEL_DARK, AMBER, 0.45),
    400: "#F6D07E",
    500: AMBER,
    600: AMBER,
    700: "#F6D07E",
    800: "#F9DE9F",
    900: "#FBE9C0",
    950: "#FDF4DF",
  } as Ramp,
  accentText: AMBER,
};

// Status hues keep Tailwind's defaults in light mode; in dark mode the pale
// badge backgrounds become tinted panels and the dark text shades brighten.
const STATUS_HUES = ["emerald", "green", "red", "rose", "amber", "yellow", "orange", "blue", "sky", "purple", "violet", "teal"] as const;

function statusDark(hue: Ramp): Ramp {
  return {
    50: mix(PANEL_DARK, hue[400], 0.1),
    100: mix(PANEL_DARK, hue[400], 0.16),
    200: mix(PANEL_DARK, hue[400], 0.28),
    300: mix(PANEL_DARK, hue[400], 0.42),
    400: hue[400],
    500: hue[500],
    600: hue[400],
    700: hue[300],
    800: hue[200],
    900: hue[100],
    950: hue[50],
  };
}

/** Ramps mix hex values and pre-mixed channel strings; emit channels for both. */
function norm(v: string): string {
  return v.startsWith("#") ? channels(v) : v;
}

function toVars(name: string, r: Ramp): Record<string, string> {
  return Object.fromEntries(SHADES.map((s) => [`--c-${name}-${s}`, norm(r[s])]));
}

function themeVars(t: typeof light | typeof dark, isDark: boolean): Record<string, string> {
  const vars: Record<string, string> = {
    "--c-canvas": channels(t.canvas),
    "--c-white": channels(t.white),
    "--c-accent": channels(AMBER),
    "--c-on-accent": "26 20 6",
    "--c-accent-text": channels(t.accentText),
    ...toVars("slate", t.slate),
    ...toVars("indigo", t.indigo),
  };
  for (const hue of STATUS_HUES) {
    const base = defaultColors[hue] as Ramp;
    Object.assign(vars, toVars(hue, isDark ? statusDark(base) : base));
  }
  return vars;
}

function varRamp(name: string): Record<number, string> {
  return Object.fromEntries(SHADES.map((s) => [s, `rgb(var(--c-${name}-${s}) / <alpha-value>)`]));
}

const token = (name: string) => `rgb(var(--c-${name}) / <alpha-value>)`;

const config: Config = {
  darkMode: "class",
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        white: token("white"),
        slate: varRamp("slate"),
        indigo: varRamp("indigo"),
        ...Object.fromEntries(STATUS_HUES.map((h) => [h, varRamp(h)])),
        canvas: token("canvas"),
        panel: token("white"),
        ink: "rgb(var(--c-slate-900) / <alpha-value>)",
        muted: "rgb(var(--c-slate-500) / <alpha-value>)",
        line: "rgb(var(--c-slate-200) / <alpha-value>)",
        accent: {
          DEFAULT: token("accent"),
          text: token("accent-text"),
        },
        "on-accent": token("on-accent"),
        brand: varRamp("indigo"),
      },
      fontFamily: {
        sans: ["var(--font-sans)", "Inter", "system-ui", "sans-serif"],
        display: ["var(--font-display)", "var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      boxShadow: {
        soft: "0 1px 2px rgb(0 0 0 / 0.06), 0 12px 32px rgb(0 0 0 / 0.08)",
        glow: "0 8px 22px rgb(var(--c-accent) / 0.35)",
      },
      animation: {
        "pulse-dot": "pulse-dot 1.5s ease-in-out infinite",
        "logo-spin": "logo-spin 8s linear infinite",
        "screen-in": "screen-in 0.35s cubic-bezier(0.16,1,0.3,1) both",
      },
      keyframes: {
        "pulse-dot": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.3" },
        },
        "logo-spin": {
          from: { transform: "rotate(0deg)" },
          to: { transform: "rotate(360deg)" },
        },
        "screen-in": {
          from: { opacity: "0", transform: "translateY(10px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
    },
  },
  plugins: [
    // tailwindcss-animate is CJS and ships no type declarations, so an ESM `import` here
    // breaks `tsc --noEmit` (TS7016). Tailwind loads this config through jiti, where
    // require() is the supported form.
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    require("tailwindcss-animate"),
    plugin(({ addBase }) => {
      addBase({
        ":root": { ...themeVars(light, false), colorScheme: "light" },
        ".dark": { ...themeVars(dark, true), colorScheme: "dark" },
      });
    }),
  ],
};
export default config;
