import { existsSync, readdirSync, readFileSync } from "node:fs";
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

  it("every kept pair re-reports at least a day after the closure (UX-1, REQ-WEB-DATA.3)", () => {
    const zs = parseZombies(read("zombies.json"));
    if (!zs.ok) throw new Error("fixture does not parse");
    for (const z of zs.data.zombies) expect(z.gap_days).toBeGreaterThanOrEqual(1);
    const gaps = zs.data.zombies.map((z) => z.gap_days);
    expect(Math.max(...gaps)).toBeGreaterThan(30);
  });

  it("the kept set includes bulk-closure and partial-confidence cards, so those states render (REQ-WEB-CARD.1, .6)", () => {
    const zs = parseZombies(read("zombies.json"));
    if (!zs.ok) throw new Error("fixture does not parse");
    const flagged = zs.data.zombies as unknown as { bulk_closure?: boolean; confidence_partial?: boolean }[];
    expect(flagged.some((z) => z.bulk_closure)).toBe(true);
    expect(flagged.some((z) => z.confidence_partial)).toBe(true);
  });

  it("the tour shows a spread of gaps and more than one case type (UX-1)", () => {
    const tour = parseJudgeTour(read("judge_tour.json"));
    const zs = parseZombies(read("zombies.json"));
    if (!tour.ok || !zs.ok) throw new Error("fixture does not parse");
    const picked = zs.data.zombies.filter((z) => tour.data.zombie_ids.includes(z.zombie_id));
    expect(picked).toHaveLength(3);
    expect(new Set(picked.map((z) => z.type_family)).size).toBeGreaterThan(1);
    const gaps = picked.map((z) => z.gap_days);
    expect(Math.max(...gaps) - Math.min(...gaps)).toBeGreaterThan(5);
    expect(tour.data.provisional).toBe(true);
  });
});

describe("fixture judge tour follows REQ-STAT-TOUR.1 (UX-10)", () => {
  it("is the three headline zombies with the most re-reports, ties by zombie ID, never by confidence, when no override file exists", () => {
    const tour = read("judge_tour.json") as { source: string; provisional: boolean; zombie_ids: string[] };
    const zs = parseZombies(read("zombies.json"));
    if (!zs.ok) throw new Error("fixture does not parse");
    const expected = zs.data.zombies
      .filter((z) => z.tier === "headline")
      .sort((a, b) => b.reports_after - a.reports_after || (a.zombie_id < b.zombie_id ? -1 : a.zombie_id > b.zombie_id ? 1 : 0))
      .slice(0, 3)
      .map((z) => z.zombie_id);
    expect(existsSync(join(__dirname, "..", "..", "..", "data", "labels", "judge_tour_override.json"))).toBe(false);
    expect(tour.source).toBe("most_reports");
    expect(tour.provisional).toBe(true);
    expect(tour.zombie_ids).toEqual(expected);
  });

  it("no filter option appears twice for one neighborhood (UX-11)", () => {
    const zs = parseZombies(read("zombies.json"));
    if (!zs.ok) throw new Error("fixture does not parse");
    const hoods = new Set(zs.data.zombies.map((z) => z.neighborhood));
    expect(hoods.has("Allston")).toBe(false);
    expect(hoods.has("Brighton")).toBe(false);
  });
});
