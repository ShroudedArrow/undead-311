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
