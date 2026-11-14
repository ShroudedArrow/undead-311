import type { Rate, Scorecard } from "./parse";

/** "83.1%" from a 0..1 rate; empty string for null. */
export function pct(rate: number | null | undefined): string {
  return rate === null || rate === undefined ? "" : `${(rate * 100).toFixed(1)}%`;
}

export interface ShownRate {
  rate: Rate;
  /** Which stayed-fixed number is shown as the headline number (REQ-WEB-SCORE.2). */
  kind: "adjusted" | "raw";
}

/** The stayed-fixed number to show: the adjusted rate when it exists, else the raw rate (REQ-WEB-SCORE.2). */
export function stayedFixedShown(s: Scorecard): ShownRate {
  return s.stayed_fixed_adj ? { rate: s.stayed_fixed_adj, kind: "adjusted" } : { rate: s.stayed_fixed_raw, kind: "raw" };
}

/** Headline-tier scorecards, citywide ("all") first, then families by name (REQ-WEB-SCORE.1). */
export function headlineScorecards(all: readonly Scorecard[]): Scorecard[] {
  const set = all.filter((s) => s.tier_set === "headline");
  return [...set].sort((a, b) => (a.family === "all" ? -1 : b.family === "all" ? 1 : a.family < b.family ? -1 : 1));
}
