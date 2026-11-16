/**
 * On-demand data (REQ-WEB-DATA.3, REQ-EXP-SIZE.3-4). The first view loads `points.json` (headline tier only). Everything else
 * is a separate file that a page asks for when it needs it:
 *  - the other tiers, as `points/<tier>.json`, when the tier switch is on;
 *  - zombie records, as `zombies/<neighborhood>-<year>.json` shards listed in `zombies/index.json`, for the shards a table or a
 *    CSV download needs.
 * Every file goes through `loadOnce`, so a shard is fetched once per page view.
 */
import { useEffect, useMemo, useState } from "react";
import { loadOnce, useData, type Load } from "./data";
import { TIERS, type Tier } from "./filter";
import { parsePoints, parseShardIndex, parseZombies, type PointsFile, type ShardEntry, type ZombiesFile } from "./parse";

/** The tiers that are not in `points.json`; each one is its own file. */
export const EXTRA_TIERS: readonly Tier[] = TIERS.filter((t) => t !== "headline");
export const pointsFileOf = (tier: Tier): string => (tier === "headline" ? "points.json" : `points/${tier}.json`);

const COLUMNS = ["id", "lat", "lon", "tier", "family", "department", "neighborhood", "year", "date"] as const;

/** Append the columns of `more` to `base` (pure; used when other tiers are switched on). */
export function mergePoints(base: PointsFile, more: readonly PointsFile[]): PointsFile {
  const out = structuredClone(base) as Record<string, unknown> & PointsFile;
  const withDate = base.date !== undefined && more.every((m) => m.date !== undefined);
  for (const m of more) {
    for (const c of COLUMNS) {
      if (c === "date" && !withDate) continue;
      (out[c] as unknown[]).push(...((m as Record<string, unknown>)[c] as unknown[]));
    }
    out.n += m.n;
  }
  if (!withDate) delete out.date;
  return out;
}

export interface PointsState {
  /** The headline points, plus the other tiers once they have arrived. */
  load: Load<PointsFile>;
  /** The other tiers were asked for and have not all arrived. */
  pending: boolean;
  /** The first problem with a tier file, when there is one. */
  extraError: { file: string; error: string } | null;
}

/** Headline points, and the other tiers' files only when `withOtherTiers` is true (REQ-EXP-SIZE.4). */
export function usePoints(withOtherTiers: boolean): PointsState {
  const head = useData("points.json", parsePoints);
  const [extra, setExtra] = useState<Load<PointsFile[]>>({ status: "loading" });
  useEffect(() => {
    if (!withOtherTiers) return;
    let live = true;
    setExtra({ status: "loading" });
    void Promise.all(EXTRA_TIERS.map((t) => loadOnce(pointsFileOf(t), parsePoints))).then((rs) => {
      if (!live) return;
      const bad = rs.find((r) => r.status === "error");
      if (bad && bad.status === "error") setExtra({ status: "error", file: bad.file, error: bad.error });
      else setExtra({ status: "ok", data: rs.flatMap((r) => (r.status === "ok" ? [r.data] : [])) });
    });
    return () => {
      live = false;
    };
  }, [withOtherTiers]);
  return useMemo<PointsState>(() => {
    if (head.status !== "ok" || !withOtherTiers) return { load: head, pending: false, extraError: null };
    if (extra.status === "loading") return { load: head, pending: true, extraError: null };
    if (extra.status === "error") return { load: head, pending: false, extraError: { file: extra.file, error: extra.error } };
    return { load: { status: "ok", data: mergePoints(head.data, extra.data) }, pending: false, extraError: null };
  }, [head, extra, withOtherTiers]);
}

/** The zombie shard index (`zombies/index.json`): shard, neighborhood, year, size and districts of every shard. */
export function useZombieIndex(enabled = true) {
  return useData(enabled ? "zombies/index.json" : null, parseShardIndex);
}

const CONCURRENCY = 6;

/** Load `files` (at most CONCURRENCY at a time) and join their zombies in the order of `files`. */
export async function loadZombieShards(files: readonly string[]): Promise<Load<ZombiesFile>> {
  const results: Load<ZombiesFile>[] = new Array(files.length);
  let next = 0;
  const worker = async () => {
    while (next < files.length) {
      const i = next++;
      results[i] = await loadOnce(files[i], parseZombies);
    }
  };
  await Promise.all(Array.from({ length: Math.min(CONCURRENCY, files.length) }, worker));
  const bad = results.find((r) => r.status === "error");
  if (bad && bad.status === "error") return bad;
  const ok = results.flatMap((r) => (r.status === "ok" ? [r.data] : []));
  return { status: "ok", data: { data_version: ok[0]?.data_version ?? "", zombies: ok.flatMap((d) => d.zombies) } };
}

/** `zombies/<key>.json` for each shard key. */
export const zombieShardFile = (key: string): string => `zombies/${key}.json`;

/**
 * Zombie records for the given shard keys (`<neighborhood slug>-<year>`), loaded when `keys` is not null. A table or CSV that
 * needs every zombie passes every key of the index (`allShardKeys`).
 */
export function useZombieShards(keys: readonly string[] | null): Load<ZombiesFile> {
  const [state, setState] = useState<Load<ZombiesFile>>({ status: "loading" });
  const sig = keys === null ? null : [...new Set(keys)].sort().join("|");
  useEffect(() => {
    if (sig === null) return;
    let live = true;
    setState({ status: "loading" });
    void loadZombieShards(sig === "" ? [] : sig.split("|").map(zombieShardFile)).then((r) => live && setState(r));
    return () => {
      live = false;
    };
  }, [sig]);
  return state;
}

export const allShardKeys = (shards: readonly ShardEntry[]): string[] => shards.map((s) => s.shard);
