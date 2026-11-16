import { afterEach, describe, expect, it, vi } from "vitest";
import { clearDataCache } from "./data";
import { EXTRA_TIERS, loadZombieShards, mergePoints, pointsFileOf, zombieShardFile } from "./shards";
import type { PointsFile } from "./parse";

const pts = (ids: string[], tier: string, withDate = true): PointsFile =>
  ({ data_version: "v", n: ids.length, id: ids, lat: ids.map(() => 42.3), lon: ids.map(() => -71), tier: ids.map(() => tier), family: ids.map(() => "sign"), department: ids.map(() => null), neighborhood: ids.map(() => "Roxbury"), year: ids.map(() => 2024), ...(withDate ? { date: ids.map(() => "2024-01-02") } : {}) }) as PointsFile;

afterEach(() => { vi.unstubAllGlobals(); clearDataCache(); });

describe("on-demand data (REQ-EXP-SIZE.3-4)", () => {
  it("names one file per extra tier and none for the headline tier's extras", () => {
    expect(pointsFileOf("headline")).toBe("points.json");
    expect(EXTRA_TIERS.map(pointsFileOf)).toEqual(["points/source_unknown.json", "points/city_rereport.json", "points/sensitivity.json"]);
    expect(zombieShardFile("roxbury-2024")).toBe("zombies/roxbury-2024.json");
  });
  it("merges tier files into the headline points without changing the first file", () => {
    const head = pts(["a", "b"], "headline");
    const merged = mergePoints(head, [pts(["c"], "city_rereport"), pts([], "sensitivity")]);
    expect(merged.n).toBe(3);
    expect(merged.id).toEqual(["a", "b", "c"]);
    for (const col of [merged.lat, merged.lon, merged.tier, merged.family, merged.department, merged.neighborhood, merged.year, merged.date ?? []]) expect(col).toHaveLength(3);
    expect(head.n).toBe(2);
  });
  it("drops the date column when a tier file has none, so the columns stay parallel", () => {
    const merged = mergePoints(pts(["a"], "headline"), [pts(["b"], "city_rereport", false)]);
    expect(merged.date).toBeUndefined();
    expect(merged.id).toHaveLength(2);
  });
  it("loads each shard once and joins them in order; one bad shard is an error naming its file", async () => {
    const fn = vi.fn(async (u: string) => {
      const k = /zombies\/([a-z0-9-]+)\.json$/.exec(String(u))?.[1] ?? "";
      return { ok: k !== "bad", status: k === "bad" ? 404 : 200, json: async () => ({ data_version: "v", shard: k, zombies: [] }) } as Response;
    });
    vi.stubGlobal("fetch", fn);
    const ok = await loadZombieShards(["zombies/a-2020.json", "zombies/b-2021.json", "zombies/a-2020.json"]);
    expect(ok.status).toBe("ok");
    expect(fn).toHaveBeenCalledTimes(2);
    const bad = await loadZombieShards(["zombies/bad.json"]);
    expect(bad).toMatchObject({ status: "error", file: "zombies/bad.json" });
  });
});
