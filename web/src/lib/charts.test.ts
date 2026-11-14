import { readFileSync } from "node:fs";
import { join } from "node:path";
import fc from "fast-check";
import { describe, expect, it } from "vitest";
import { curveKind, curvesFor, intensityText, isUnusual, isValidCurve, leaderboard, limitAt, linePath, linear, logScale } from "./charts";
import { parseFunnel, parseGroups, parseSurvival, type FunnelLimit, type Group } from "./parse";

const read = (f: string): unknown => JSON.parse(readFileSync(join(__dirname, "..", "..", "public", "data", f), "utf8"));

const limit = (n: number, lo998: number, hi998: number): FunnelLimit => ({ n, lo95: lo998 + 0.01, hi95: hi998 - 0.01, lo998, hi998 });
const LIMITS: FunnelLimit[] = [limit(1, 0, 1), limit(10, 0.02, 0.4), limit(100, 0.06, 0.2), limit(1000, 0.08, 0.12)];
const grp = (over: Partial<Group>): Group => ({ kind: "neighborhood", name: "x", n: 100, k: 10, raw: 0.1, shrunk: 0.1, lo: 0.05, hi: 0.15, unusual: false, reports_per_km: null, ...over });

describe("curve names (REQ-WEB-CHARTS.1)", () => {
  it("reads kind prefixes and falls back to the known family keys", () => {
    expect(curveKind("all")).toEqual({ kind: "all", key: "all" });
    expect(curveKind("family:sign")).toEqual({ kind: "family", key: "sign" });
    expect(curveKind("department:PWDx")).toEqual({ kind: "department", key: "PWDx" });
    expect(curveKind("sidewalk").kind).toBe("family");
    expect(curveKind("PWDx").kind).toBe("department");
  });
  it("selects by tier set and kind", () => {
    const base = { times: [0], survival: [1], lo: [1], hi: [1], at_7: null, at_30: null, at_90: null, half_life: null };
    const cs = [
      { ...base, name: "all", tier_set: "headline" as const },
      { ...base, name: "family:sign", tier_set: "headline" as const },
      { ...base, name: "family:sign", tier_set: "all" as const },
      { ...base, name: "department:BTDT", tier_set: "headline" as const },
    ];
    expect(curvesFor(cs, "headline", "family").map((c) => c.name)).toEqual(["family:sign"]);
    expect(curvesFor(cs, "all", "family")).toHaveLength(1);
    expect(curvesFor(cs, "headline", "department").map((c) => c.name)).toEqual(["department:BTDT"]);
  });
});

describe("survival curve check (testing.md #6)", () => {
  it("accepts a curve that starts at 1 and falls, rejects a rise or a start below 1", () => {
    expect(isValidCurve({ survival: [1, 0.9, 0.9, 0.5] })).toBe(true);
    expect(isValidCurve({ survival: [1, 0.9, 0.95] })).toBe(false);
    expect(isValidCurve({ survival: [0.9, 0.8] })).toBe(false);
    expect(isValidCurve({ survival: [] })).toBe(false);
  });
  it("every curve in the fixture survival.json starts at 1, never rises and keeps its interval around the estimate", () => {
    const f = parseSurvival(read("survival.json"));
    if (!f.ok) throw new Error(f.error);
    expect(f.data.curves.length).toBeGreaterThan(0);
    for (const c of f.data.curves) {
      expect(isValidCurve(c), c.name).toBe(true);
      for (let i = 0; i < c.survival.length; i++) {
        expect(c.lo[i]).toBeLessThanOrEqual(c.survival[i]);
        expect(c.hi[i]).toBeGreaterThanOrEqual(c.survival[i]);
      }
    }
  });
});

describe("Property W9: only groups outside the 99.8% limits are unusual (REQ-WEB-CHARTS.2)", () => {
  it("a group inside the limits is never shown as unusual, even if the file flags it", () => {
    fc.assert(
      fc.property(fc.integer({ min: 1, max: 3000 }), fc.double({ min: 0, max: 1, noNaN: true }), (n, raw) => {
        const l = limitAt(LIMITS, n) as FunnelLimit;
        const g = { n, raw, unusual: true };
        const outside = raw < l.lo998 || raw > l.hi998;
        expect(isUnusual(g, LIMITS)).toBe(outside);
      }),
    );
  });
  it("a group the file does not flag is never shown as unusual", () => {
    fc.assert(
      fc.property(fc.integer({ min: 1, max: 3000 }), fc.double({ min: 0, max: 1, noNaN: true }), (n, raw) => {
        expect(isUnusual({ n, raw, unusual: false }, LIMITS)).toBe(false);
      }),
    );
  });
  it("uses the wider limits of the next smaller listed n, and handles a null rate", () => {
    expect(limitAt(LIMITS, 50)?.n).toBe(10);
    expect(isUnusual({ n: 50, raw: null, unusual: true }, LIMITS)).toBe(false);
    expect(isUnusual({ n: 50, raw: 0.3, unusual: true }, [])).toBe(false);
  });
  it("the fixture funnel agrees: every unusual group lies outside its limits and the limits nest", () => {
    const f = parseFunnel(read("funnel.json"));
    if (!f.ok) throw new Error(f.error);
    for (const l of f.data.limits) {
      expect(l.lo998).toBeLessThanOrEqual(l.lo95);
      expect(l.hi998).toBeGreaterThanOrEqual(l.hi95);
    }
    for (const g of f.data.groups) if (g.unusual) expect(isUnusual(g, f.data.limits), g.name).toBe(true);
  });
});

describe("leaderboard (REQ-WEB-CHARTS.2)", () => {
  it("orders by the shrunk rate, never the raw rate, and keeps raw and n on every row", () => {
    const rows = leaderboard(
      [grp({ name: "small", n: 2, raw: 1, shrunk: 0.12 }), grp({ name: "big", n: 900, raw: 0.2, shrunk: 0.19 }), grp({ kind: "family", name: "other" })],
      "neighborhood",
      LIMITS,
    );
    expect(rows.map((r) => r.name)).toEqual(["big", "small"]);
    for (const r of rows) expect(r.n).toBeGreaterThan(0);
  });
  it("is sorted by shrunk for any input and lists each group once", () => {
    fc.assert(
      fc.property(fc.array(fc.record({ n: fc.integer({ min: 1, max: 500 }), shrunk: fc.double({ min: 0, max: 1, noNaN: true }) }), { maxLength: 25 }), (xs) => {
        const groups = xs.map((x, i) => grp({ name: `g${i}`, n: x.n, shrunk: x.shrunk }));
        const rows = leaderboard(groups, "neighborhood", LIMITS);
        expect(rows).toHaveLength(groups.length);
        for (let i = 1; i < rows.length; i++) expect((rows[i - 1].shrunk as number) >= (rows[i].shrunk as number)).toBe(true);
      }),
    );
  });
  it("reports missing reporting intensity as null, not as a number", () => {
    expect(intensityText({ reports_per_km: null })).toBeNull();
    expect(intensityText({ reports_per_km: 12.345 })).toBe("12.3");
  });
  it("fixture groups: the shrunk rate lies between the raw rate and the citywide rate", () => {
    const g = parseGroups(read("groups.json"));
    if (!g.ok) throw new Error(g.error);
    const c = g.data.citywide as number;
    for (const x of g.data.groups) {
      if (x.raw === null || x.shrunk === null) continue;
      expect(x.shrunk).toBeGreaterThanOrEqual(Math.min(x.raw, c) - 1e-4);
      expect(x.shrunk).toBeLessThanOrEqual(Math.max(x.raw, c) + 1e-4);
    }
  });
});

describe("scales and paths", () => {
  it("maps the ends of a domain to the ends of the range", () => {
    expect(linear(0, 10, 100, 200)(0)).toBe(100);
    expect(linear(0, 10, 100, 200)(10)).toBe(200);
    expect(logScale(1, 100, 0, 200)(10)).toBeCloseTo(100);
    expect(linePath([0, 1], [2, 3])).toBe("M0.0 2.0 L1.0 3.0");
  });
});
