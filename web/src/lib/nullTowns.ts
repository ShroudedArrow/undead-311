/**
 * Null-town results for the methods page (REQ-WEB-METHODS.1; owner decision on issue 130 of the channel repo, option 1 with conditions).
 * A null town is a seeded synthetic town where every report arrives by chance and none is a resurrection, so the true
 * excess is 0. These figures are copied from the table in docs/METHODS.md ("Durability statistics"); `nullTowns.test.ts`
 * recomputes every row from that file, so the page cannot drift from the document.
 */
export interface NullTownRow {
  /** Key of the display label in en.json (`methods.nt_<id>`). */
  id: string;
  /** The town's label in docs/METHODS.md, used by the pinning test. */
  doc: string;
  seeds: string;
  below: number;
  covers: number;
  above: number;
  /** Smallest and largest excess over the seeds. */
  min: number;
  max: number;
}

export const NULL_TOWNS: readonly NullTownRow[] = [
  { id: "gap30", doc: "Report every 30 days (Poisson)", seeds: "5-8", below: 4, covers: 0, above: 0, min: -855, max: -643 },
  { id: "gap45", doc: "Report every 45 days", seeds: "5-8", below: 4, covers: 0, above: 0, min: -739, max: -613 },
  { id: "gap60", doc: "Report every 60 days", seeds: "5-8", below: 4, covers: 0, above: 0, min: -688, max: -480 },
  { id: "mixed2", doc: "Each spot every 30 or 60 days", seeds: "5-10", below: 6, covers: 0, above: 0, min: -715, max: -559 },
  { id: "mixed5", doc: "Each spot every 30, 60, 120, 250 or 400 days", seeds: "5-12", below: 8, covers: 0, above: 0, min: -398, max: -300 },
  { id: "sparse300", doc: "Sparse: every 300 days", seeds: "5-8", below: 0, covers: 4, above: 0, min: -29, max: -3 },
  { id: "sparse400", doc: "Sparse: every 400 days", seeds: "5-8", below: 1, covers: 3, above: 0, min: -34, max: 16 },
  { id: "season60", doc: "Seasonal (winter 2x, summer 0.25x), base 60 days", seeds: "5-6", below: 2, covers: 0, above: 0, min: -403, max: -324 },
  { id: "season200", doc: "Seasonal, base 200 days", seeds: "5-6", below: 2, covers: 0, above: 0, min: -100, max: -94 },
  { id: "season400", doc: "Seasonal, base 400 days", seeds: "5-6", below: 1, covers: 1, above: 0, min: -54, max: -20 },
];

export const sumOf = (key: "below" | "covers" | "above"): number => NULL_TOWNS.reduce((s, r) => s + r[key], 0);

/** Signed whole number with an ASCII sign, as in docs/METHODS.md. */
export function signed(v: number): string {
  return v > 0 ? `+${v}` : String(v);
}

/** The second set of towns in docs/METHODS.md, built to stress the method: 48 towns, 18 with the interval above 0 (pinned by the test). */
export const STRESS_TOWNS = 48;
export const STRESS_ABOVE = 18;
