import { describe, expect, it } from "vitest";
import type { PointRow } from "../lib/points";
import { buildLayers, hitRadius, markerSize, MIN_HIT_RADIUS_PX } from "./layers";
import { DENSITY_ZOOM } from "./density";

const row = (id: string): PointRow => ({ id, lat: 42.35, lon: -71.06, tier: "headline" }) as unknown as PointRow;
const atlas = {} as HTMLCanvasElement;
const base = { rows: [row("a"), row("b")], selectedId: null, atlas, bulkIds: new Set(["a"]), onSelect: () => {} };
const ids = (x: ReturnType<typeof buildLayers>) => x.map((l) => l.id);

describe("map layer order (REQ-WEB-MAP.1, decision 11, issue 190)", () => {
  it("draws the bulk rings under the markers", () => {
    expect(ids(buildLayers(base))).toEqual(["bulk-ring-edge", "bulk-ring", "zombie-halo", "zombies", "zombie-hit", "clusters", "cluster-count", "cluster-hit"]);
  });

  it("draws only the markers when the bulk layer is off", () => {
    expect(ids(buildLayers({ ...base, bulkIds: null }))).toEqual(["zombie-halo", "zombies", "zombie-hit", "clusters", "cluster-count", "cluster-hit"]);
  });

  it("has no neighborhood label layer, since the names collided on the hero map (issue 190)", () => {
    expect(ids(buildLayers(base))).not.toContain("place-labels");
  });

  it("keeps the markers pickable so a click opens the card, through the invisible hit circles", () => {
    const by = Object.fromEntries(buildLayers(base).map((l) => [l.id, l]));
    expect(by["zombie-hit"].props.pickable).toBe(true);
    expect(by["zombie-halo"].props.pickable).toBe(true);
    expect(by["zombies"].props.pickable).toBeFalsy(); // transparent pixels are unpickable, so the sprite is not what is picked
  });
});

describe("marker size on a phone (UX-60, REQ-WEB-MAP.1)", () => {
  it("is smaller on a phone, and a selected marker is always larger than the others", () => {
    expect(markerSize(false, true)).toBeLessThan(markerSize(false, false));
    expect(markerSize(true, true)).toBeGreaterThan(markerSize(false, true));
    expect(markerSize(true, false)).toBeGreaterThan(markerSize(false, false));
  });
});

describe("hit areas cover the whole circle (REQ-WEB-MAP.1, REQ-WEB-A11Y.1)", () => {
  const layers = () => Object.fromEntries(buildLayers(base).map((l) => [l.id, l]));
  it("draws the halo under the sprites and the core over them, so a visible marker under the pointer always wins over a halo", () => {
    const order = buildLayers(base).map((l) => l.id);
    expect(order.indexOf("zombie-halo")).toBeLessThan(order.indexOf("zombies"));
    expect(order.indexOf("zombies")).toBeLessThan(order.indexOf("zombie-hit"));
  });
  it("uses the same data in the same order in all three, so overlapping markers pick the one drawn last", () => {
    const l = layers();
    expect(l["zombie-hit"].props.data).toBe(l["zombies"].props.data);
    expect(l["zombie-halo"].props.data).toBe(l["zombies"].props.data);
  });
  it("is invisible: a fully transparent fill, no stroke", () => {
    for (const id of ["zombie-halo", "zombie-hit"]) {
      const p = layers()[id].props as unknown as { getFillColor: number[]; stroked: boolean };
      expect(p.getFillColor[3]).toBe(0);
      expect(p.stroked).toBe(false);
    }
  });
  it("covers the painted circle on every screen and is at least 44 px across on a phone", () => {
    for (const compact of [false, true]) for (const selected of [false, true]) {
      expect(hitRadius(selected, compact)).toBeGreaterThanOrEqual(markerSize(selected, compact) / 2);
    }
    expect(hitRadius(false, true) * 2).toBeGreaterThanOrEqual(2 * MIN_HIT_RADIUS_PX);
    expect(MIN_HIT_RADIUS_PX * 2).toBe(44);
  });
  it("selects through either circle", () => {
    const picked: string[] = [];
    const l = Object.fromEntries(buildLayers({ ...base, onSelect: (id) => picked.push(id) }).map((x) => [x.id, x]));
    for (const id of ["zombie-halo", "zombie-hit"]) (l[id].props as unknown as { onClick: (i: unknown) => void }).onClick({ object: { id: "b" } });
    expect(picked).toEqual(["b", "b"]);
  });
});

describe("density view and zoom-scaled markers (REQ-WEB-MAP.1)", () => {
  const near = (id: string, dx: number): PointRow => ({ id, lat: 42.35, lon: -71.06 + dx, tier: "headline", family: "sign" }) as unknown as PointRow;
  const dense = { ...base, bulkIds: null, rows: [near("a", 0), near("b", 0.00005), near("c", 0.0001), near("far", 0.5)] };
  const by = (zoom: number | undefined, extra = {}) => Object.fromEntries(buildLayers({ ...dense, zoom, ...extra }).map((l) => [l.id, l]));
  const data = (l: { props: unknown }) => (l.props as { data: unknown[] }).data;

  it("draws every marker on its own with no clusters at the threshold and above, and with no zoom given", () => {
    for (const z of [undefined, DENSITY_ZOOM, 16]) {
      expect(data(by(z)["zombies"])).toHaveLength(4);
      expect(data(by(z)["clusters"])).toHaveLength(0);
    }
  });
  it("groups close markers into one cluster below the threshold and keeps a far one as a marker", () => {
    const l = by(11.2);
    expect(data(l["clusters"])).toHaveLength(1);
    expect((data(l["clusters"])[0] as { count: number }).count).toBe(3);
    expect(data(l["zombies"]).map((r) => (r as PointRow).id)).toEqual(["far"]);
    expect(data(l["cluster-hit"])).toBe(data(l["clusters"]));
    expect(data(l["cluster-count"])).toBe(data(l["clusters"]));
  });
  it("keeps the selected marker out of any cluster", () => {
    const l = by(11.2, { selectedId: "b" });
    expect(data(l["zombies"]).map((r) => (r as PointRow).id).sort()).toEqual(["b", "far"]);
  });
  it("makes a cluster click call back with the cluster, and the hit circles stay invisible", () => {
    const got: string[] = [];
    const l = by(11.2, { onCluster: (c: { ids: string[] }) => got.push(c.ids.join(",")) });
    (l["cluster-hit"].props as unknown as { onClick: (i: unknown) => void }).onClick({ object: data(l["clusters"])[0] });
    expect(got).toEqual(["a,b,c"]);
    expect((l["cluster-hit"].props as unknown as { getFillColor: number[] }).getFillColor[3]).toBe(0);
  });
  it("scales unselected markers with the zoom but never the selected one, and keeps a 44 px phone target", () => {
    expect(markerSize(false, false, DENSITY_ZOOM)).toBeLessThan(markerSize(false, false, DENSITY_ZOOM + 2));
    expect(markerSize(false, false, DENSITY_ZOOM + 2)).toBe(30);
    expect(markerSize(true, false, 9)).toBe(44);
    expect(markerSize(false, true, DENSITY_ZOOM)).toBeCloseTo(18.2);
    expect(hitRadius(false, true, DENSITY_ZOOM) * 2).toBeGreaterThanOrEqual(44);
    for (const z of [9, 11.2, DENSITY_ZOOM, 15]) expect(hitRadius(false, false, z)).toBeGreaterThanOrEqual(markerSize(false, false, z) / 2);
  });
  it("markers are never drawn smaller than their minimum so the letter stays a letter", () => {
    const p = by(DENSITY_ZOOM)["zombies"].props as unknown as { sizeMinPixels: number };
    expect(p.sizeMinPixels).toBeGreaterThanOrEqual(16);
  });
});

describe("time-lapse markers never cluster and grow with zoom (REQ-WEB-TIMELAPSE.1)", () => {
  const near = (id: string, dx: number): PointRow => ({ id, lat: 42.35, lon: -71.06 + dx, tier: "headline", family: "sign" }) as unknown as PointRow;
  const rows = [near("a", 0), near("b", 0.00005), near("c", 0.0001)];
  const layer = (zoom: number) => Object.fromEntries(buildLayers({ ...base, bulkIds: null, rows, zoom, mode: "dots" }).map((l) => [l.id, l]));
  const data = (l: { props: unknown }) => (l.props as { data: unknown[] }).data;
  it("draws every possible zombie on its own at city zoom", () => {
    expect(data(layer(11.2)["clusters"])).toHaveLength(0);
    expect(data(layer(11.2)["zombies"])).toHaveLength(3);
  });
  it("draws small plain rings at city zoom and full stencil circles zoomed in", () => {
    expect(markerSize(false, false, 11.2, "dots")).toBeLessThan(13);
    expect(markerSize(false, false, 11.2, "dots")).toBeLessThan(markerSize(false, false, 11.2, "density"));
    expect(markerSize(false, false, 14.5, "dots")).toBe(30);
    expect(markerSize(false, false, 12, "dots")).toBeGreaterThan(markerSize(false, false, 11, "dots"));
    // zoomed out to the floor the dots keep shrinking, so the core reads as dots, not a blob (reviewer-ux r4 F1)
    expect(markerSize(false, true, 9.2, "dots")).toBeLessThan(markerSize(false, true, 11.2, "dots") * 0.6);
    expect(markerSize(false, true, 9.2, "dots")).toBeGreaterThanOrEqual(3);
    for (let z = 8; z < 15; z += 0.25) expect(markerSize(false, false, z + 0.25, "dots")).toBeGreaterThanOrEqual(markerSize(false, false, z, "dots"));
    const icon = (zoom: number) => (layer(zoom)["zombies"].props as unknown as { getIcon: (d: PointRow) => string }).getIcon(rows[0]);
    expect(icon(11.2)).toMatch(/^other-/); // no letter at city zoom
    expect(icon(14)).toMatch(/^sign-/);
    expect((layer(11.2)["zombies"].props as unknown as { sizeMinPixels: number }).sizeMinPixels).toBeLessThan(10);
  });
});
