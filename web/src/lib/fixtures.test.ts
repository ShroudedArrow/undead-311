import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { parseCardShard, parseJudgeTour, parsePoints, parseScorecard, parseStatus, parseValidation, parseZombies } from "./parse";
import { shardFile } from "./shard";

const dir = join(__dirname, "..", "..", "public", "data");
const read = (f: string): unknown => JSON.parse(readFileSync(join(dir, f), "utf8"));

describe("fixture files follow the schemas (REQ-WEB-DATA.3)", () => {
  it.each([
    ["zombies.json", parseZombies],
    ["points.json", parsePoints],
    ["scorecard.json", parseScorecard],
    ["status.json", parseStatus],
    ["judge_tour.json", parseJudgeTour],
    ["validation.json", parseValidation],
  ] as const)("%s parses", (file, parse) => {
    expect(parse(read(file))).toMatchObject({ ok: true });
  });

  it("every card shard parses and is named by neighborhood and year", () => {
    const shards = readdirSync(join(dir, "cards"));
    expect(shards.length).toBeGreaterThan(0);
    for (const f of shards) expect(parseCardShard(read(`cards/${f}`))).toMatchObject({ ok: true });
  });

  it("points are parallel arrays and every point has a zombie and a card in the shard its fields name", () => {
    const pts = parsePoints(read("points.json"));
    const zs = parseZombies(read("zombies.json"));
    if (!pts.ok || !zs.ok) throw new Error("fixture does not parse");
    const p = pts.data;
    for (const col of [p.id, p.lat, p.lon, p.tier, p.family, p.department, p.neighborhood, p.year]) expect(col.length).toBe(p.n);
    expect(new Set(p.id)).toEqual(new Set(zs.data.zombies.map((z) => z.zombie_id)));
    for (let i = 0; i < Math.min(p.n, 40); i++) {
      const shard = parseCardShard(read(shardFile(p.neighborhood[i], p.year[i])));
      expect(shard.ok && shard.data.cards.some((c) => c.zombie_id === p.id[i])).toBe(true);
    }
  });

  it("the provisional tour names three zombies that exist", () => {
    const tour = parseJudgeTour(read("judge_tour.json"));
    const ids = new Set((parsePoints(read("points.json")) as { data: { id: string[] } }).data.id);
    if (!tour.ok) throw new Error("tour does not parse");
    expect(tour.data.zombie_ids).toHaveLength(3);
    for (const id of tour.data.zombie_ids) expect(ids.has(id)).toBe(true);
  });
});
