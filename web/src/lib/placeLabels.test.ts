import fc from "fast-check";
import { describe, expect, it } from "vitest";
import { neighborhoodLabels } from "./placeLabels";
import type { PointRow } from "./points";

const row = (id: string, neighborhood: string | null, lat: number, lon: number): PointRow => ({ id, neighborhood, lat, lon, tier: "headline", family: "pothole_roadway", department: "PWDx", year: 2024 });

describe("neighborhood map labels (ops#18, REQ-WEB-MAP.1)", () => {
  it("places the name at the median point, so one far-off case does not move it", () => {
    const out = neighborhoodLabels([row("a", "Dorchester", 42.3, -71.07), row("b", "Dorchester", 42.31, -71.06), row("c", "Dorchester", 42.32, -71.05), row("d", "Dorchester", 42.5, -70.9)]);
    expect(out).toEqual([{ name: "Dorchester", lat: 42.315, lon: -71.055, count: 4 }]);
  });
  it("skips neighborhoods with too few points and rows with no neighborhood", () => {
    const out = neighborhoodLabels([row("a", "Roxbury", 42.3, -71.1), row("b", "Roxbury", 42.3, -71.1), row("c", null, 42.3, -71.1), row("d", null, 42.3, -71.1), row("e", null, 42.3, -71.1)]);
    expect(out).toEqual([]);
  });
  it("property: one label per neighborhood, sorted, inside the box of its points, and input order does not matter", () => {
    const r = fc.record({ n: fc.constantFrom("A", "B", "C", null), lat: fc.double({ min: 42.2, max: 42.4, noNaN: true }), lon: fc.double({ min: -71.2, max: -70.9, noNaN: true }) });
    fc.assert(
      fc.property(fc.array(r, { maxLength: 40 }), (xs) => {
        const rows = xs.map((x, i) => row(`z${i}`, x.n, x.lat, x.lon));
        const out = neighborhoodLabels(rows, 1);
        const names = out.map((l) => l.name);
        expect(names).toEqual([...new Set(names)].sort());
        for (const l of out) {
          const mine = rows.filter((x) => x.neighborhood === l.name);
          expect(l.count).toBe(mine.length);
          expect(l.lat).toBeGreaterThanOrEqual(Math.min(...mine.map((x) => x.lat)));
          expect(l.lat).toBeLessThanOrEqual(Math.max(...mine.map((x) => x.lat)));
        }
        expect(neighborhoodLabels([...rows].reverse(), 1)).toEqual(out);
      }),
    );
  });
});
