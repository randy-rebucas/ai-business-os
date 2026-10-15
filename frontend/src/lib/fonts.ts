import {
  Archivo,
  Bricolage_Grotesque,
  Familjen_Grotesk,
  Figtree,
  Hanken_Grotesk,
  JetBrains_Mono,
  Public_Sans,
  Schibsted_Grotesk,
  Source_Sans_3,
  Source_Serif_4,
} from "next/font/google";

// Type moods (backend abos/branding/moods.py — keys must match). The platform's own voice is "report"; the others are
// declared but only downloaded by a browser when a workspace's mood actually uses them (preload: false).
const reportDisplay = Schibsted_Grotesk({ subsets: ["latin"], variable: "--font-report-display", display: "swap" });
const reportText = Public_Sans({ subsets: ["latin"], variable: "--font-report-text", display: "swap" });
const marketDisplay = Bricolage_Grotesque({ subsets: ["latin"], variable: "--font-market-display", display: "swap", preload: false });
const marketText = Figtree({ subsets: ["latin"], variable: "--font-market-text", display: "swap", preload: false });
const worksDisplay = Archivo({ subsets: ["latin"], variable: "--font-works-display", display: "swap", preload: false, axes: ["wdth"] });
const careDisplay = Source_Serif_4({ subsets: ["latin"], variable: "--font-care-display", display: "swap", preload: false });
const careText = Source_Sans_3({ subsets: ["latin"], variable: "--font-care-text", display: "swap", preload: false });
const studioDisplay = Familjen_Grotesk({ subsets: ["latin"], variable: "--font-studio-display", display: "swap", preload: false });
const studioText = Hanken_Grotesk({ subsets: ["latin"], variable: "--font-studio-text", display: "swap", preload: false });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jetbrains", display: "swap", preload: false });

export const fontVariables = [reportDisplay, reportText, marketDisplay, marketText, worksDisplay, careDisplay, careText,
  studioDisplay, studioText, mono].map((f) => f.variable).join(" ");

export type MoodKey = "report" | "market" | "works" | "care" | "studio";

/** CSS values for --mood-display / --mood-text (see globals.css). "works" uses Archivo for both. */
export const MOOD_FONTS: Record<MoodKey, { display: string; text: string }> = {
  report: { display: "var(--font-report-display)", text: "var(--font-report-text)" },
  market: { display: "var(--font-market-display)", text: "var(--font-market-text)" },
  works: { display: "var(--font-works-display)", text: "var(--font-works-display)" },
  care: { display: "var(--font-care-display)", text: "var(--font-care-text)" },
  studio: { display: "var(--font-studio-display)", text: "var(--font-studio-text)" },
};
