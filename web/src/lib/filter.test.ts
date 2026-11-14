import fc from "fast-check";
import { describe, expect, it } from "vitest";
import { aggregate, applyFilters, EMPTY_FILTERS, matches, options, UNKNOWN, visibleSet, type FilterableZombie, type Filters, type GroupBy } from "./filter";

const HOODS = ["Dorchester", "Roxbury", "Back Bay", null];
const DEPTS = ["PWDx", "BTDT", null];
const FAMS = ["pothole_roadway", "streetlight", "sidewalk"];
const arbZombie = fc.record({
  id: fc.uuid(),
  tier: fc.constantFrom("headline", "source_unknown", "sensitivity"),
  family: fc.constantFrom(...FAMS),
  department: fc.constantFrom(...DEPTS),
  neighborhood: fc.constantFrom(...HOODS),
  year: fc.integer({ min: 2015, max: 2026 }),
}) as fc.Arbitrary<FilterableZombie>;
const arbZombies = fc.uniqueArray(arbZombie, { selector: (z) => z.id, maxLength: 60 });
const arbFilters: fc.Arbitrary<Filters> = fc.record({
  neighborhoods: fc.subarray(["Dorchester", "Roxbury", "Back Bay", UNKNOWN]),
  departments: fc.subarray(["PWDx", "BTDT", UNKNOWN]),
  families: fc.subarray(FAMS),
  years: fc.subarray([2015, 2018, 2020, 2022, 2024, 2026]),
});
const arbMode = fc.constantFrom("headline", "all") as fc.Arbitrary<"headline" | "all">;

describe("Property W2: the filter result is a subset (REQ-WEB-MAP.2)", () => {
  it("returns a subset in input order", () => {
    fc.assert(
      fc.property(arbZombies, arbFilters, arbMode, (zs, f, mode) => {
        const out = applyFilters(zs, f, mode);
        const ids = new Set(zs.map((z) => z.id));
        expect(out.every((z) => ids.has(z.id))).toBe(true);
        expect(out.map((z) => z.id)).toEqual(zs.filter((z) => out.includes(z)).map((z) => z.id));
        expect(out.length).toBeLessThanOrEqual(zs.length);
      }),
    );
  });
  it("with empty filters and the all tier mode returns the input", () => {
    fc.assert(
      fc.property(arbZombies, (zs) => {
        expect(applyFilters(zs, EMPTY_FILTERS, "all")).toEqual(zs);
      }),
    );
  });
  it("headline mode never contains another tier (REQ-WEB-MAP.4)", () => {
    fc.assert(
      fc.property(arbZombies, arbFilters, (zs, f) => {
        expect(applyFilters(zs, f, "headline").every((z) => z.tier === "headline")).toBe(true);
      }),
    );
  });
});

describe("Property W3: filters commute and are idempotent (REQ-WEB-MAP.3)", () => {
  it("applying A then B equals B then A equals items that match both", () => {
    fc.assert(
      fc.property(arbZombies, arbFilters, arbFilters, arbMode, (zs, a, b, mode) => {
        const ab = applyFilters(applyFilters(zs, a, mode), b, mode);
        const ba = applyFilters(applyFilters(zs, b, mode), a, mode);
        const both = zs.filter((z) => matches(z, a) && matches(z, b) && (mode === "all" || z.tier === "headline"));
        expect(ab).toEqual(ba);
        expect(ab).toEqual(both);
      }),
    );
  });
  it("applying the same filter twice changes nothing", () => {
    fc.assert(
      fc.property(arbZombies, arbFilters, arbMode, (zs, f, mode) => {
        const once = applyFilters(zs, f, mode);
        expect(applyFilters(once, f, mode)).toEqual(once);
      }),
    );
  });
});

describe("Property W5: aggregate counts (REQ-WEB-MAP.2)", () => {
  it("sum to the filtered total and are never negative", () => {
    fc.assert(
      fc.property(arbZombies, arbFilters, arbMode, fc.constantFrom<GroupBy>("neighborhood", "department", "family", "year"), (zs, f, mode, by) => {
        const filtered = applyFilters(zs, f, mode);
        const counts = aggregate(filtered, by);
        expect(counts.reduce((s, c) => s + c.count, 0)).toBe(filtered.length);
        expect(counts.every((c) => c.count > 0 && Number.isInteger(c.count))).toBe(true);
        expect(new Set(counts.map((c) => c.key)).size).toBe(counts.length);
      }),
    );
  });
  it("is sorted by count then key, deterministically", () => {
    const zs: FilterableZombie[] = [
      { id: "1", tier: "headline", family: "sign", department: null, neighborhood: "B", year: 2020 },
      { id: "2", tier: "headline", family: "sign", department: null, neighborhood: "A", year: 2020 },
      { id: "3", tier: "headline", family: "sign", department: null, neighborhood: "A", year: 2021 },
    ];
    expect(aggregate(zs, "neighborhood")).toEqual([{ key: "A", count: 2 }, { key: "B", count: 1 }]);
    expect(aggregate(zs, "department")).toEqual([{ key: UNKNOWN, count: 3 }]);
    expect(options(zs, "year")).toEqual(["2020", "2021"]);
  });
});

describe("visibleSet (REQ-WEB-MAP.4, REQ-WEB-TIER.2)", () => {
  it("reports the headline count whatever the tier mode, and it never exceeds the all-tier count", () => {
    fc.assert(
      fc.property(arbZombies, arbFilters, (zs, f) => {
        const h = visibleSet(zs, f, "headline");
        const a = visibleSet(zs, f, "all");
        expect(h.headlineCount).toBe(a.headlineCount);
        expect(h.items.length).toBe(h.headlineCount);
        expect(a.items.length).toBe(a.allCount);
        expect(a.headlineCount).toBeLessThanOrEqual(a.allCount);
      }),
    );
  });
});
