/**
 * Filtering and aggregation (REQ-WEB-MAP.2-4, REQ-WEB-TABLE.1). Pure functions; the map, the table and the count all call
 * `visibleSet`, so they can never disagree (property W4).
 */
/**
 * Every tier, in display order. The `Tier` type is derived from this list, so a tier cannot exist without being listed here,
 * and the copy test (REQ-WEB-TIER.1) requires a label and a card note for each (UX-55).
 */
export const TIERS = ["headline", "source_unknown", "city_rereport", "sensitivity"] as const;
export type Tier = (typeof TIERS)[number];
/** "headline" shows the headline tier only (REQ-WEB-MAP.4); "all" adds the other tiers (REQ-WEB-TIER). */
export type TierMode = "headline" | "all";

export interface Filters {
  neighborhoods: string[];
  departments: string[];
  families: string[];
  years: number[];
}

/** The fields a zombie needs to be filtered. A null neighborhood or department is matched by the UNKNOWN key. */
export interface FilterableZombie {
  id: string;
  tier: Tier;
  family: string;
  department: string | null;
  neighborhood: string | null;
  year: number;
}

export const UNKNOWN = "unknown";
export const EMPTY_FILTERS: Filters = { neighborhoods: [], departments: [], families: [], years: [] };

export type GroupBy = "neighborhood" | "department" | "family" | "year";
export interface Count {
  key: string;
  count: number;
}

const keyOf = (v: string | null): string => (v === null || v === "" ? UNKNOWN : v);

/** True when `item` passes every non-empty filter dimension (empty dimension = all). */
export function matches(item: FilterableZombie, f: Filters): boolean {
  return (
    (f.neighborhoods.length === 0 || f.neighborhoods.includes(keyOf(item.neighborhood))) &&
    (f.departments.length === 0 || f.departments.includes(keyOf(item.department))) &&
    (f.families.length === 0 || f.families.includes(item.family)) &&
    (f.years.length === 0 || f.years.includes(item.year))
  );
}

/** Subset of `items` that passes the filters and the tier mode, in input order (REQ-WEB-MAP.2, .4). */
export function applyFilters<T extends FilterableZombie>(items: readonly T[], filters: Filters, tierMode: TierMode): T[] {
  return items.filter((i) => (tierMode === "all" || i.tier === "headline") && matches(i, filters));
}

/** Counts per group over `items`, biggest first, ties by key. The counts sum to items.length. */
export function aggregate(items: readonly FilterableZombie[], by: GroupBy): Count[] {
  const m = new Map<string, number>();
  for (const i of items) {
    const key = by === "year" ? String(i.year) : by === "family" ? i.family : keyOf(by === "neighborhood" ? i.neighborhood : i.department);
    m.set(key, (m.get(key) ?? 0) + 1);
  }
  return [...m.entries()].map(([key, count]) => ({ key, count })).sort((a, b) => b.count - a.count || (a.key < b.key ? -1 : 1));
}

export interface VisibleSet<T extends FilterableZombie> {
  /** What the map draws, the table lists and the count counts. */
  items: T[];
  /** Headline-tier zombies that pass the filters, whatever the tier mode (always shown first, REQ-WEB-TIER.2). */
  headlineCount: number;
  /** All-tier zombies that pass the filters. */
  allCount: number;
}

export function visibleSet<T extends FilterableZombie>(items: readonly T[], filters: Filters, tierMode: TierMode): VisibleSet<T> {
  return {
    items: applyFilters(items, filters, tierMode),
    headlineCount: applyFilters(items, filters, "headline").length,
    allCount: applyFilters(items, filters, "all").length,
  };
}

/** Distinct values of a group over `items`, for filter menus. Years ascend; other groups sort by name. */
export function options(items: readonly FilterableZombie[], by: GroupBy): string[] {
  const keys = [...new Set(aggregate(items, by).map((c) => c.key))];
  return by === "year" ? keys.sort((a, b) => Number(a) - Number(b)) : keys.sort();
}
