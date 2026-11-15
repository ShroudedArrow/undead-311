import { describe, expect, it } from "vitest";
import type { PointRow } from "../lib/points";
import { buildLayers } from "./layers";

const row = (id: string): PointRow => ({ id, lat: 42.35, lon: -71.06, tier: "headline" }) as unknown as PointRow;
const atlas = {} as HTMLCanvasElement;
const base = { rows: [row("a"), row("b")], selectedId: null, atlas, bulkIds: new Set(["a"]), onSelect: () => {} };
const ids = (x: ReturnType<typeof buildLayers>) => x.map((l) => l.id);

describe("map layer order (REQ-WEB-MAP.1, decision 11, issue 190)", () => {
  it("draws the bulk rings under the markers", () => {
    expect(ids(buildLayers(base))).toEqual(["bulk-ring-edge", "bulk-ring", "zombies"]);
  });

  it("draws only the markers when the bulk layer is off", () => {
    expect(ids(buildLayers({ ...base, bulkIds: null }))).toEqual(["zombies"]);
  });

  it("has no neighborhood label layer, since the names collided on the hero map (issue 190)", () => {
    expect(ids(buildLayers(base))).not.toContain("place-labels");
  });

  it("keeps the markers pickable so a click opens the card", () => {
    expect(buildLayers(base).find((x) => x.id === "zombies")?.props.pickable).toBe(true);
  });
});
