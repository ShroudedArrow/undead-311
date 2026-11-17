/**
 * Readers for the methods page (REQ-WEB-METHODS.1). The shift-test distribution and the placebo result are optional
 * extra fields of excess.json (the schema allows extras); a missing or malformed field returns null, so the page says so
 * instead of showing a made-up number.
 */
import type { ExcessFile, ExcessRow } from "./parse";

export interface ShiftResult {
  runs: number;
  seed: number | null;
  observed: number;
  mean: number;
  q025: number;
  q975: number;
}
export interface PlaceboResult {
  excess: number;
  lo: number;
  hi: number;
}

const num = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

export function readShift(file: ExcessFile): ShiftResult | null {
  const s = file.shift as Record<string, unknown> | undefined;
  if (!s || typeof s !== "object") return null;
  if (!num(s.runs) || !num(s.observed) || !num(s.mean) || !num(s.q025) || !num(s.q975)) return null;
  return { runs: s.runs, seed: num(s.seed) ? s.seed : null, observed: s.observed, mean: s.mean, q025: s.q025, q975: s.q975 };
}

export function readPlacebo(file: ExcessFile): PlaceboResult | null {
  const p = file.placebo as Record<string, unknown> | undefined;
  if (!p || typeof p !== "object") return null;
  return num(p.excess) && num(p.lo) && num(p.hi) ? { excess: p.excess, lo: p.lo, hi: p.hi } : null;
}

/**
 * methods.md (Primary baseline, owner rule 2026-11-16): when the headline placebo interval does not cover 0, the excess is not
 * shown anywhere on the site and the methods page shows the placebo result instead. A file with no placebo shows no excess either:
 * an excess is only shown once its calibration check has run and passed.
 */
export function excessShown(file: ExcessFile | null | undefined): boolean {
  if (!file) return false;
  const p = readPlacebo(file);
  return p !== null && p.lo <= 0 && p.hi >= 0;
}

/** Headline-tier family rows, biggest excess first (ties by name). */
export function familyExcessRows(file: ExcessFile): ExcessRow[] {
  return file.rows
    .filter((r) => r.kind === "family" && r.tier_set === "headline")
    .sort((a, b) => b.excess - a.excess || (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
}

/** One decimal for counts, trimming a trailing ".0". */
export function num1(v: number): string {
  return (Math.round(v * 10) / 10).toFixed(1).replace(/\.0$/, "");
}
