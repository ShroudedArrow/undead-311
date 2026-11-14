/** Table rows and sorting (REQ-WEB-TABLE.1). Rows come from the same visible set as the map and the count (property W4). */
import type { Tier } from "./filter";
import type { PointRow } from "./points";
import type { Zombie } from "./parse";

export type SortKey = "date" | "gap" | "neighborhood" | "family" | "confidence";
export type SortDir = "asc" | "desc";

export interface TableRow {
  id: string;
  /** ISO date when the zombie file has it, else the year. */
  date: string;
  gap: number | null;
  neighborhood: string;
  family: string;
  confidence: number | null;
  /** Which tier counts it; shown as text so color is never the only signal (REQ-WEB-TIER.1). */
  tier: Tier;
  /** Present only while the bulk-closure layer is on: whether the original's closure was part of a bulk closure. */
  bulk?: boolean;
}

export function buildTableRows(items: readonly PointRow[], zombies: ReadonlyMap<string, Zombie> | null, withBulk = false): TableRow[] {
  return items.map((p) => {
    const z = zombies?.get(p.id);
    return {
      id: p.id,
      date: z?.resurrection_date ?? String(p.year),
      gap: z ? z.gap_days : null,
      neighborhood: p.neighborhood ?? "",
      family: p.family,
      confidence: z ? z.confidence : null,
      tier: p.tier,
      ...(withBulk ? { bulk: bulkOf(z) } : {}),
    };
  });
}

const cmp = (a: string | number, b: string | number): number => (a < b ? -1 : a > b ? 1 : 0);

/** Stable sort, ties broken by id. Missing numbers sort last in both directions. */
export function sortRows(rows: readonly TableRow[], key: SortKey, dir: SortDir): TableRow[] {
  const sign = dir === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    const av = a[key];
    const bv = b[key];
    if (av === null && bv !== null) return 1;
    if (bv === null && av !== null) return -1;
    const c = av === null || bv === null ? 0 : sign * cmp(av, bv);
    return c !== 0 ? c : cmp(a.id, b.id);
  });
}

/** True when the zombie's closure was flagged as part of a bulk closure (REQ-WEB-DEATHS.1). */
export function bulkOf(z: Zombie | undefined): boolean {
  return (z as { bulk_closure?: boolean } | undefined)?.bulk_closure === true;
}

/** IDs of the visible zombies whose closure was part of a bulk closure. Empty until the zombie file has loaded. */
export function bulkIds(items: readonly PointRow[], zombies: ReadonlyMap<string, Zombie> | null): Set<string> {
  return new Set(zombies ? items.filter((p) => bulkOf(zombies.get(p.id))).map((p) => p.id) : []);
}
