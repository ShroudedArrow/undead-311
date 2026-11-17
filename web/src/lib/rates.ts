import type { Rate, Scorecard } from "./parse";

/** "83.1%" from a 0..1 rate; empty string for null. */
export function pct(rate: number | null | undefined): string {
  return rate === null || rate === undefined ? "" : `${(rate * 100).toFixed(1)}%`;
}

export interface ShownRate {
  rate: Rate;
  /** Which stayed-fixed number is shown (REQ-WEB-SCORE.2): always the raw rate. */
  kind: "raw";
}

/**
 * The stayed-fixed number to show beside the on-time rate: the raw rate only (owner decision 2026-11-17). The adjusted rate
 * depends on the same uncalibrated baseline as the excess, so the site never shows it, even when a file carries one.
 */
export function stayedFixedShown(s: Scorecard): ShownRate {
  return { rate: s.stayed_fixed_raw, kind: "raw" };
}

/** Headline-tier scorecards, citywide ("all") first, then families by name (REQ-WEB-SCORE.1). */
export function headlineScorecards(all: readonly Scorecard[]): Scorecard[] {
  const set = all.filter((s) => s.tier_set === "headline");
  return [...set].sort((a, b) => (a.family === "all" ? -1 : b.family === "all" ? 1 : a.family < b.family ? -1 : 1));
}
