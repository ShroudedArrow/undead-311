/**
 * Repeat offenders view (REQ-WEB-REPEAT.1): chains with at least REPEAT_MIN_HEADLINE headline possible zombies, as the engine exports
 * them in `repeat_offenders.json`. `times_risen` counts the chain's possible zombies in all tiers and can be higher than the headline count.
 */
import type { PointRow } from "./points";
import type { RepeatOffendersFile, Zombie } from "./parse";

export const REPEAT_MIN_HEADLINE = 3;
export type Chain = RepeatOffendersFile["repeat_offenders"][number];

/** Most returns first, then most headline zombies, then chain ID (stable). Chains below the minimum are dropped, never shown. */
export function sortChains(chains: readonly Chain[]): Chain[] {
  return chains
    .filter((c) => c.headline_count >= REPEAT_MIN_HEADLINE)
    .sort((a, b) => b.times_risen - a.times_risen || b.headline_count - a.headline_count || (a.chain_id < b.chain_id ? -1 : a.chain_id > b.chain_id ? 1 : 0));
}

export type ChainSortKey = "where" | "type" | "times" | "headline";
const CHAIN_SORT_KEYS: readonly ChainSortKey[] = ["where", "type", "times", "headline"];

/** Sort key and direction from the URL (`sort`, `dir`). The default is the order `sortChains` gives: most returns first. */
export function decodeChainSort(params: URLSearchParams): { key: ChainSortKey; dir: "asc" | "desc" } {
  const k = params.get("sort") as ChainSortKey | null;
  if (!k || !CHAIN_SORT_KEYS.includes(k)) return { key: "times", dir: "desc" };
  return { key: k, dir: params.get("dir") === "asc" ? "asc" : "desc" };
}

/** Chains ordered by one column; ties keep the default order (most returns, most headline, chain ID), so the sort is stable and repeatable. */
export function sortChainsBy(chains: readonly Chain[], key: ChainSortKey, dir: "asc" | "desc"): Chain[] {
  const base = sortChains(chains);
  if (key === "times" && dir === "desc") return base;
  const sign = dir === "asc" ? 1 : -1;
  const value = (c: Chain): string | number =>
    key === "where" ? (c.neighborhood ?? "").toLowerCase() : key === "type" ? (c.type_family ?? "").toLowerCase() : key === "times" ? c.times_risen : c.headline_count;
  const order = new Map(base.map((c, i) => [c, i]));
  return [...base].sort((a, b) => {
    const av = value(a);
    const bv = value(b);
    const c = av < bv ? -1 : av > bv ? 1 : 0;
    return c !== 0 ? sign * c : (order.get(a) as number) - (order.get(b) as number);
  });
}

/** One marker per chain, at the location the engine exports (block level for residential chains, REQ-EXP-PRIV). Chains with no location are left off the map. */
export function chainRows(chains: readonly Chain[]): PointRow[] {
  return chains
    .filter((c) => typeof c.lat === "number" && typeof c.lon === "number")
    .map((c) => ({
      id: c.chain_id,
      lat: c.lat as number,
      lon: c.lon as number,
      tier: "headline" as const,
      family: c.type_family ?? "unknown",
      department: null,
      neighborhood: c.neighborhood ?? null,
      year: 0,
    }));
}

/** The earliest headline possible zombie of a chain, to open its first autopsy card; null when zombies.json does not hold one. */
export function firstZombieOfChain(chainId: string, zombies: readonly Zombie[]): Zombie | null {
  const inChain = zombies.filter((z) => z.chain_id === chainId && z.tier === "headline");
  inChain.sort((a, b) => ((a.resurrection_date ?? "") < (b.resurrection_date ?? "") ? -1 : (a.resurrection_date ?? "") > (b.resurrection_date ?? "") ? 1 : a.zombie_id < b.zombie_id ? -1 : 1));
  return inChain[0] ?? null;
}
