import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { parseBulkClosures, parseCardShard, parseExcess, parseExclusions, parseFunnel, parseGroups, parseJudgeTour, parseSurvival, parseTemporaryFixes, parsePoints, parseScorecard, parseStatus, parseValidation, parseZombies } from "./parse";
import { shardFile } from "./shard";
// @ts-expect-error plain .mjs build script, no type declarations
import { buildFixtures, canonicalHood } from "../../scripts/make-fixtures.mjs";

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
    ["survival.json", parseSurvival],
    ["funnel.json", parseFunnel],
    ["groups.json", parseGroups],
    ["excess.json", parseExcess],
    ["temporary_fixes.json", parseTemporaryFixes],
    ["exclusions.json", parseExclusions],
    ["bulk_closures.json", parseBulkClosures],
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

  it("one neighborhood name per area: no Downtown or Mattapan split across systems (UX-14, REQ-WEB-MAP.2)", () => {
    const pts = parsePoints(read("points.json"));
    if (!pts.ok) throw new Error("fixture does not parse");
    const names = new Set(pts.data.neighborhood);
    expect(names.has("Downtown")).toBe(false);
    expect(names.has("Mattapan")).toBe(false);
  });

  it("stats files carry params and a seed (REQ-EXP-1.2, REQ-OPS-CI.1)", () => {
    for (const f of ["judge_tour.json", "scorecard.json"]) {
      const j = read(f) as { params?: { WINDOW_DAYS: number }; seed?: unknown };
      expect(j.params?.WINDOW_DAYS).toBe(60);
      expect(j.seed).toBeNull();
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

  it("the kept set includes partial-confidence cards, so that state renders (REQ-WEB-CARD.6)", () => {
    const zs = parseZombies(read("zombies.json"));
    if (!zs.ok) throw new Error("fixture does not parse");
    const flagged = zs.data.zombies as unknown as { confidence_partial?: boolean }[];
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

describe("fixtures follow the zombie definition (UX-16, UX-18, UX-20, UX-25)", () => {
  const TRANSFER = /resubmitted|see new case|transferred|migrated/i;
  const allCards = () => readdirSync(join(dir, "cards")).flatMap((f) => {
    const sh = parseCardShard(read(`cards/${f}`));
    if (!sh.ok) throw new Error(`${f} does not parse`);
    return sh.data.cards;
  });

  it("no card has an original closed as transferred or resubmitted: step 9 says such a case is never an original (UX-16)", () => {
    const cards = allCards();
    expect(cards.length).toBeGreaterThan(0);
    for (const c of cards) expect(TRANSFER.test(c.original.closure_text ?? ""), c.zombie_id).toBe(false);
  });

  it("no card has a new-system original closed as Transitioned: step 9 says it is never an original (UX-26, testing.md property 20)", () => {
    const cards = allCards();
    for (const c of cards) {
      expect((c.original.closure_text ?? "").trim().toLowerCase(), c.zombie_id).not.toBe("transitioned");
      expect(c.original.closure_text ?? "", c.zombie_id).not.toMatch(/transition/i);
    }
  });

  it("bulk flags come from bulk_closures.json: a zombie is flagged exactly when its original's (department, day, text) is listed (UX-18)", () => {
    const bulk = parseBulkClosures(read("bulk_closures.json"));
    const zs = parseZombies(read("zombies.json"));
    if (!bulk.ok || !zs.ok) throw new Error("fixture does not parse");
    const listed = new Set(bulk.data.bulk_closures.map((b) => `${b.close_date}|${b.template}`));
    const byId = new Map(allCards().map((c) => [c.zombie_id, c]));
    for (const z of zs.data.zombies) {
      const o = byId.get(z.zombie_id)?.original;
      const inBulk = o !== undefined && o.close_time != null && listed.has(`${o.close_time.slice(0, 10)}|${(o.closure_text ?? "").trim()}`);
      expect(z.bulk_closure === true, z.zombie_id).toBe(inBulk);
    }
    if (bulk.data.bulk_closures.length === 0) expect(zs.data.zombies.some((z) => z.bulk_closure)).toBe(false);
  });

  it("one name per area and no 'Boston' neighborhood: Fenway, Longwood and South Boston parts are merged, unassigned cases are null (UX-20)", () => {
    const g = parseGroups(read("groups.json"));
    const pts = parsePoints(read("points.json"));
    if (!g.ok || !pts.ok) throw new Error("fixture does not parse");
    const names = new Set([...g.data.groups.filter((x) => x.kind === "neighborhood").map((x) => x.name), ...pts.data.neighborhood.filter((x): x is string => x !== null)]);
    for (const bad of ["Boston", "Fenway", "Longwood", "South Boston", "South Boston Waterfront"]) expect(names.has(bad), bad).toBe(false);
  });

  it("the methods numbers describe the same zombies as the map: observed headline = status headline_count (UX-25)", () => {
    const ex = read("excess.json") as { shift: { observed: number } };
    const st = parseStatus(read("status.json"));
    if (!st.ok) throw new Error("fixture does not parse");
    expect(ex.shift.observed).toBe(st.data.headline_count);
    const zs = parseZombies(read("zombies.json"));
    if (!zs.ok) throw new Error("fixture does not parse");
    expect(zs.data.zombies.filter((z) => z.tier === "headline")).toHaveLength(st.data.headline_count as number);
  });
});

type Row = Record<string, string>;
const row = (over: Row): Row => ({
  id: "1", system: "legacy", open_time_utc: "2020-01-01T10:00:00Z", close_time_utc: "2020-01-02T10:00:00Z", status: "Closed", closure_text: "Case Closed Case Resolved Work done.",
  closure_code: "", type_raw: "Pothole", type_family: "pothole_roadway", city_originated_type: "false", department: "PWDx", neighborhood: "Dorchester", street: "1 A St",
  lat: "42.3", lon: "-71.06", source: "Constituent Call", ...over,
});
const build = (rows: Row[]) => (buildFixtures as (r: Row[], o?: unknown) => { files: Record<string, { zombies?: { zombie_id: string; bulk_closure: boolean }[]; bulk_closures?: unknown[] }> })(rows);

describe("fixture builder rules (UX-16, UX-18, UX-20)", () => {
  it("keeps a pair after an ordinary closure and drops one whose original was resubmitted or transferred (ZD step 9)", () => {
    const re = (id: string, lat: string) => row({ id, open_time_utc: "2020-01-10T10:00:00Z", close_time_utc: "", status: "Open", lat });
    const ok = build([row({ id: "a" }), re("b", "42.3")]).files["zombies.json"].zombies ?? [];
    expect(ok.map((z) => z.zombie_id)).toEqual(["I-a:b"]);
    for (const text of ["Case Closed Resubmitted as BCS-12345", "Closed. See new case BCS-9", "Transferred to the new system", "Migrated"]) {
      const gone = build([row({ id: "a", closure_text: text }), re("b", "42.3")]).files["zombies.json"].zombies ?? [];
      expect(gone, text).toEqual([]);
    }
  });
  it("drops a pair whose new-system original was closed with code Transitioned, by code or by text (ZD step 9, UX-26)", () => {
    const re = row({ id: "b", system: "new", open_time_utc: "2020-01-10T10:00:00Z", close_time_utc: "", status: "Open" });
    for (const over of [{ closure_code: "Transitioned" }, { closure_text: "Transitioned" }] as Row[]) {
      const gone = build([row({ id: "a", system: "new", ...over }), re]).files["zombies.json"].zombies ?? [];
      expect(gone, JSON.stringify(over)).toEqual([]);
    }
    const kept = build([row({ id: "a", system: "new", closure_code: "Noted", closure_text: "Noted" }), re]).files["zombies.json"].zombies ?? [];
    expect(kept.map((z) => z.zombie_id)).toEqual(["I-a:b"]);
  });
  it("flags bulk_closure only for originals in a listed (department, day, template) group, and lists that group (UX-18)", () => {
    const text = "Case Closed Case Noted Backlog cleanup.";
    const bulk = Array.from({ length: 50 }, (_, i) => row({ id: `x${i}`, closure_text: text, close_time_utc: "2020-03-05T12:00:00Z", open_time_utc: "2020-01-01T10:00:00Z", lat: String(42.3 + i * 0.01) }));
    const usual = Array.from({ length: 5 }, (_, i) => row({ id: `u${i}`, closure_text: text, close_time_utc: `2020-02-0${i + 1}T12:00:00Z`, lat: String(43 + i * 0.01) }));
    const rr = (id: string, lat: string, open: string) => row({ id, open_time_utc: open, close_time_utc: "", status: "Open", lat });
    const f = build([...bulk, ...usual, rr("r0", "42.3", "2020-03-20T10:00:00Z"), rr("r1", "43", "2020-02-20T10:00:00Z")]).files;
    expect((f["bulk_closures.json"].bulk_closures ?? []).length).toBe(1);
    const flags = Object.fromEntries((f["zombies.json"].zombies ?? []).map((z) => [z.zombie_id, z.bulk_closure]));
    expect(flags).toEqual({ "I-x0:r0": true, "I-u0:r1": false });
  });
  it("merges split neighborhood names and gives 'Boston' no neighborhood (UX-20)", () => {
    expect(canonicalHood("Fenway")).toBe(canonicalHood("Longwood"));
    expect(canonicalHood("South Boston")).toBe(canonicalHood("South Boston Waterfront"));
    expect(canonicalHood("Boston")).toBeNull();
    expect(canonicalHood("Dorchester")).toBe("Dorchester");
    expect(canonicalHood("")).toBeNull();
  });
});
