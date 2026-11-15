import { describe, expect, it } from "vitest";
import type { PlaceLabel } from "../lib/placeLabels";
import type { PointRow } from "../lib/points";
import { buildLayers } from "./layers";

const row = (id: string): PointRow => ({ id, lat: 42.35, lon: -71.06, tier: "headline" }) as unknown as PointRow;
const labels: PlaceLabel[] = [{ name: "Fenway", lat: 42.34, lon: -71.1, count: 5 }];
const atlas = {} as HTMLCanvasElement;
const base = { rows: [row("a"), row("b")], selectedId: null, atlas, bulkIds: new Set(["a"]), labels, fontReady: true, onSelect: () => {} };
const ids = (x: ReturnType<typeof buildLayers>) => x.map((l) => l.id);

describe("map layer order (REQ-WEB-MAP.1, ops#18, UX-47)", () => {
  it("draws place-labels last, above the bulk rings and the markers", () => {
    expect(ids(buildLayers(base))).toEqual(["bulk-ring-edge", "bulk-ring", "zombies", "place-labels"]);
  });

  it("keeps place-labels last when the bulk layer is off", () => {
    expect(ids(buildLayers({ ...base, bulkIds: null }))).toEqual(["zombies", "place-labels"]);
  });

  it("leaves labels out until the font is ready or when there are none", () => {
    expect(ids(buildLayers({ ...base, fontReady: false }))).not.toContain("place-labels");
    expect(ids(buildLayers({ ...base, labels: [] }))).not.toContain("place-labels");
  });

  it("does not make labels pickable, so a click reaches the marker under a name", () => {
    const l = buildLayers(base).find((x) => x.id === "place-labels");
    expect(l?.props.pickable).toBe(false);
  });
});
