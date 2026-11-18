import { describe, expect, it } from "vitest";
import type { PointRow } from "../lib/points";
import { buildLayers, hitRadius, markerSize, MIN_HIT_RADIUS_PX } from "./layers";

const row = (id: string): PointRow => ({ id, lat: 42.35, lon: -71.06, tier: "headline" }) as unknown as PointRow;
const atlas = {} as HTMLCanvasElement;
const base = { rows: [row("a"), row("b")], selectedId: null, atlas, bulkIds: new Set(["a"]), onSelect: () => {} };
const ids = (x: ReturnType<typeof buildLayers>) => x.map((l) => l.id);

describe("map layer order (REQ-WEB-MAP.1, decision 11, issue 190)", () => {
  it("draws the bulk rings under the markers", () => {
    expect(ids(buildLayers(base))).toEqual(["bulk-ring-edge", "bulk-ring", "zombie-halo", "zombies", "zombie-hit"]);
  });

  it("draws only the markers when the bulk layer is off", () => {
    expect(ids(buildLayers({ ...base, bulkIds: null }))).toEqual(["zombie-halo", "zombies", "zombie-hit"]);
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
