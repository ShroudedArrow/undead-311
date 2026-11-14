/**
 * URL state for the map page (REQ-WEB-MAP.3; permalinks are completed in REQ-WEB-LINKS).
 * Filters, tier mode and view live in the query string, so a link reproduces the screen.
 */
import { EMPTY_FILTERS, type Filters, type TierMode } from "./filter";

export type View = "map" | "table";
export interface PageState {
  filters: Filters;
  tierMode: TierMode;
  view: View;
  /** Optional map layer: mark possible zombies whose closure was part of a bulk closure (REQ-WEB-DEATHS.1). */
  bulk: boolean;
}

export const DEFAULT_STATE: PageState = { filters: EMPTY_FILTERS, tierMode: "headline", view: "map", bulk: false };

const sortedUnique = <T extends string | number>(xs: T[]): T[] => [...new Set(xs)].sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));

export function encodeState(s: PageState): string {
  const p = new URLSearchParams();
  for (const v of sortedUnique(s.filters.neighborhoods)) p.append("n", v);
  for (const v of sortedUnique(s.filters.departments)) p.append("d", v);
  for (const v of sortedUnique(s.filters.families)) p.append("f", v);
  for (const v of sortedUnique(s.filters.years)) p.append("y", String(v));
  if (s.tierMode === "all") p.set("tier", "all");
  if (s.view === "table") p.set("view", "table");
  if (s.bulk) p.set("bulk", "1");
  return p.toString();
}

export function decodeState(search: string): PageState {
  const p = new URLSearchParams(search);
  const years = p.getAll("y").map(Number).filter((n) => Number.isInteger(n));
  return {
    filters: {
      neighborhoods: sortedUnique(p.getAll("n")),
      departments: sortedUnique(p.getAll("d")),
      families: sortedUnique(p.getAll("f")),
      years: sortedUnique(years),
    },
    tierMode: p.get("tier") === "all" ? "all" : "headline",
    view: p.get("view") === "table" ? "table" : "map",
    bulk: p.get("bulk") === "1",
  };
}
