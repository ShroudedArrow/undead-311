import fc from "fast-check";
import { describe, expect, it } from "vitest";
import { visibleSet, type Filters } from "./filter";
import type { PointRow } from "./points";
import { buildTableRows, sortRows, type SortKey, type TableRow } from "./table";

const arbRow: fc.Arbitrary<PointRow> = fc.record({
  id: fc.uuid(),
  lat: fc.constant(42.3),
  lon: fc.constant(-71.1),
  tier: fc.constantFrom("headline", "source_unknown", "sensitivity"),
  family: fc.constantFrom("sign", "sidewalk", "streetlight"),
  department: fc.constantFrom("PWDx", "BTDT", null),
  neighborhood: fc.constantFrom("Dorchester", "Roxbury", null),
  year: fc.integer({ min: 2015, max: 2026 }),
});
const arbRows = fc.uniqueArray(arbRow, { selector: (r) => r.id, maxLength: 50 });
const arbFilters: fc.Arbitrary<Filters> = fc.record({
  neighborhoods: fc.subarray(["Dorchester", "Roxbury", "unknown"]),
  departments: fc.subarray(["PWDx", "BTDT", "unknown"]),
  families: fc.subarray(["sign", "sidewalk", "streetlight"]),
  years: fc.subarray([2015, 2020, 2026]),
});

describe("Property W4: map set = table set = counted set (REQ-WEB-MAP.3, REQ-WEB-TABLE.1)", () => {
  it("holds for any filters and tier mode", () => {
    fc.assert(
      fc.property(arbRows, arbFilters, fc.constantFrom("headline", "all"), (rows, f, mode) => {
        const v = visibleSet(rows, f, mode);
        const mapIds = v.items.map((r) => r.id);
        const tableIds = buildTableRows(v.items, null).map((r) => r.id);
        const counted = mode === "headline" ? v.headlineCount : v.allCount;
        expect(tableIds).toEqual(mapIds);
        expect(counted).toBe(mapIds.length);
      }),
    );
  });
});

const arbTableRow: fc.Arbitrary<TableRow> = fc.record({
  id: fc.uuid(),
  date: fc.constantFrom("2020-01-01", "2021-05-05", "2022"),
  gap: fc.option(fc.double({ min: 0, max: 60, noNaN: true }), { nil: null }),
  neighborhood: fc.constantFrom("A", "B", ""),
  family: fc.constantFrom("sign", "sidewalk"),
  confidence: fc.option(fc.double({ min: 0, max: 1, noNaN: true }), { nil: null }),
});

describe("sortRows (REQ-WEB-TABLE.1)", () => {
  const keys: SortKey[] = ["date", "gap", "neighborhood", "family", "confidence"];
  it("keeps the same rows, whatever the key and direction", () => {
    fc.assert(
      fc.property(fc.uniqueArray(arbTableRow, { selector: (r) => r.id, maxLength: 30 }), fc.constantFrom(...keys), fc.constantFrom("asc", "desc"), (rows, k, d) => {
        const out = sortRows(rows, k, d);
        expect(out.map((r) => r.id).sort()).toEqual(rows.map((r) => r.id).sort());
      }),
    );
  });
  it("orders ascending and descending, with missing numbers last", () => {
    const rows: TableRow[] = [
      { id: "a", date: "2020", gap: 5, neighborhood: "A", family: "sign", confidence: 0.5 },
      { id: "b", date: "2021", gap: null, neighborhood: "B", family: "sign", confidence: null },
      { id: "c", date: "2019", gap: 1, neighborhood: "A", family: "sign", confidence: 0.9 },
    ];
    expect(sortRows(rows, "gap", "asc").map((r) => r.id)).toEqual(["c", "a", "b"]);
    expect(sortRows(rows, "gap", "desc").map((r) => r.id)).toEqual(["a", "c", "b"]);
    expect(sortRows(rows, "neighborhood", "asc").map((r) => r.id)).toEqual(["a", "c", "b"]);
  });
});
