import fc from "fast-check";
import { describe, expect, it } from "vitest";
import type { PointRow } from "../lib/points";
import { CELL_PX, clusterLabel, MIN_CLUSTER_GAP_PX, clusterSize, DENSITY_ZOOM, groupRows, markerScale } from "./density";

const row = (id: string, lon: number, lat: number): PointRow => ({ id, lon, lat, tier: "headline", family: "sign", department: null, neighborhood: null, year: 2020 });
const pt = fc.record({ id: fc.string({ minLength: 1, maxLength: 6 }), lon: fc.double({ min: -71.2, max: -70.95, noNaN: true }), lat: fc.double({ min: 42.2, max: 42.45, noNaN: true }) });
const rowsOf = (xs: { id: string; lon: number; lat: number }[]) => [...new Map(xs.map((x) => [x.id, x])).values()].map((x) => row(x.id, x.lon, x.lat));
const items = (g: ReturnType<typeof groupRows>) => g.singles.length + g.clusters.length;

describe("density view: clusters below the zoom threshold (REQ-WEB-MAP.1)", () => {
  it("groups two close points and leaves a far one alone", () => {
    const g = groupRows([row("a", -71.06, 42.35), row("b", -71.0601, 42.3501), row("c", -71.0, 42.4)], 11.2);
    expect(g.clusters).toHaveLength(1);
    expect(g.clusters[0].ids).toEqual(["a", "b"]);
    expect(g.clusters[0].count).toBe(2);
    expect(g.singles.map((r) => r.id)).toEqual(["c"]);
  });
  it("draws every point on its own at the threshold and above", () => {
    const rows = [row("a", -71.06, 42.35), row("b", -71.0601, 42.3501)];
    expect(groupRows(rows, DENSITY_ZOOM).clusters).toEqual([]);
    expect(groupRows(rows, 16).singles).toHaveLength(2);
    expect(groupRows(rows, DENSITY_ZOOM - 0.01).clusters).toHaveLength(1);
  });
  it("never hides the selected marker inside a cluster", () => {
    const rows = [row("a", -71.06, 42.35), row("b", -71.0601, 42.3501), row("c", -71.0602, 42.3502)];
    const g = groupRows(rows, 11, "b");
    expect(g.singles.map((r) => r.id)).toContain("b");
    expect(g.clusters.flatMap((c) => c.ids)).not.toContain("b");
  });
  it("labels counts and sizes clusters within bounds", () => {
    expect(clusterLabel(7)).toBe("7");
    expect(clusterLabel(999)).toBe("999");
    expect(clusterLabel(1250)).toBe("1.3k");
    for (const n of [2, 3, 10, 100, 100000]) expect(clusterSize(n)).toBeGreaterThanOrEqual(36), expect(clusterSize(n)).toBeLessThanOrEqual(60);
    expect(clusterSize(40)).toBeGreaterThan(clusterSize(3));
  });
  it("shrinks markers as the map zooms out, never below 70% and never above full size", () => {
    expect(markerScale(DENSITY_ZOOM)).toBeCloseTo(0.7);
    expect(markerScale(DENSITY_ZOOM + 2)).toBe(1);
    expect(markerScale(8)).toBe(0.7);
    expect(markerScale(20)).toBe(1);
    expect(markerScale(Infinity)).toBe(1);
    expect(markerScale(14)).toBeGreaterThan(markerScale(13.2));
  });

  it("property: every row is drawn exactly once, as a single or in one cluster, and counts add up", () => {
    fc.assert(fc.property(fc.array(pt, { maxLength: 60 }), fc.double({ min: 8, max: 14, noNaN: true }), (xs, z) => {
      const rows = rowsOf(xs);
      const g = groupRows(rows, z);
      const ids = [...g.singles.map((r) => r.id), ...g.clusters.flatMap((c) => c.ids)];
      expect([...ids].sort()).toEqual(rows.map((r) => r.id).sort());
      for (const c of g.clusters) {
        expect(c.count).toBe(c.ids.length);
        expect(c.count).toBeGreaterThanOrEqual(2);
      }
    }));
  });
  it("property: the result does not depend on the order of the rows", () => {
    fc.assert(fc.property(fc.array(pt, { maxLength: 40 }), fc.double({ min: 8, max: 12.9, noNaN: true }), (xs, z) => {
      const rows = rowsOf(xs);
      const a = groupRows(rows, z);
      const b = groupRows([...rows].reverse(), z);
      expect(a.clusters).toEqual(b.clusters);
      expect(a.singles.map((r) => r.id).sort()).toEqual(b.singles.map((r) => r.id).sort());
    }));
  });
  it("property: zooming out one whole step never shows more items", () => {
    fc.assert(fc.property(fc.array(pt, { maxLength: 60 }), fc.integer({ min: 8, max: 12 }), (xs, z) => {
      const rows = rowsOf(xs);
      expect(items(groupRows(rows, z - 1))).toBeLessThanOrEqual(items(groupRows(rows, z)));
    }));
  });
  it("property: no two cluster badges are closer on screen than the minimum gap, so no count covers another", () => {
    fc.assert(fc.property(fc.array(pt, { maxLength: 80 }), fc.double({ min: 9, max: 12.9, noNaN: true }), (xs, z) => {
      const g = groupRows(rowsOf(xs), z);
      const zz = Math.floor(z * 2) / 2;
      const px = (c: { lon: number; lat: number }) => {
        const r = (c.lat * Math.PI) / 180;
        return [((c.lon + 180) / 360) * 512 * 2 ** zz, ((1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2) * 512 * 2 ** zz];
      };
      for (let a = 0; a < g.clusters.length; a++) for (let b = a + 1; b < g.clusters.length; b++) {
        const [ax, ay] = px(g.clusters[a]);
        const [bx, by] = px(g.clusters[b]);
        expect(Math.hypot(ax - bx, ay - by)).toBeGreaterThanOrEqual(MIN_CLUSTER_GAP_PX - 1e-6);
      }
    }));
  });
  it("property: a cluster is still a local group: its points lie within a few cells of each other on a sparse map", () => {
    fc.assert(fc.property(fc.array(pt, { maxLength: 12 }), (xs) => {
      const rows = rowsOf(xs);
      const g = groupRows(rows, 11);
      const by = new Map(rows.map((r) => [r.id, r]));
      const px = (lon: number) => ((lon + 180) / 360) * 512 * 2 ** 11;
      for (const c of g.clusters) {
        const lons = c.ids.map((id) => px(by.get(id)!.lon));
        expect(Math.max(...lons) - Math.min(...lons)).toBeLessThan(CELL_PX * 12);
      }
    }));
  });
  it("merges two clusters that sit across a cell border, so their badges never overlap", () => {
    // two pairs about 20 px apart at zoom 11, on either side of a cell line
    const z = 11;
    const lonAt = (x: number) => (x / (512 * 2 ** z)) * 360 - 180;
    const x0 = Math.ceil((((-71.06 + 180) / 360) * 512 * 2 ** z) / CELL_PX) * CELL_PX; // a cell border
    const rows = [row("a", lonAt(x0 - 12), 42.35), row("b", lonAt(x0 - 9), 42.35), row("c", lonAt(x0 + 9), 42.35), row("d", lonAt(x0 + 12), 42.35)];
    const g = groupRows(rows, z);
    expect(g.clusters).toHaveLength(1);
    expect(g.clusters[0].ids).toEqual(["a", "b", "c", "d"]);
  });
});
