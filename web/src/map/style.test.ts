import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { PALETTE } from "./palette";
import { buildStyle } from "./style";

describe("map style keeps Crew white free (REQ-WEB-DESIGN.1, UX-3)", () => {
  const style = buildStyle("pmtiles://x/tiles/boston.pmtiles", "OSM");
  it("paints no basemap layer in Crew white", () => {
    for (const layer of style.layers) {
      const paint = JSON.stringify((layer as { paint?: unknown }).paint ?? {});
      expect(paint, layer.id).not.toContain(PALETTE.crewWhite);
    }
  });
  it("outlines water and buildings in Asphalt", () => {
    const water = style.layers.find((l) => l.id === "water-edge") as { paint: Record<string, unknown> };
    expect(water.paint["line-color"]).toBe(PALETTE.asphalt);
  });
});

describe("MapLibre controls are restyled (REQ-WEB-DESIGN.2, UX-2)", () => {
  const css = readFileSync(join(__dirname, "..", "styles", "app.css"), "utf8");
  it("overrides the control group, buttons and attribution with palette tokens and no shadow", () => {
    expect(css).toContain(".maplibregl-ctrl-group");
    expect(css).toContain(".maplibregl-ctrl-attrib");
    expect(css).toMatch(/\.maplibregl-ctrl-group:not\(:empty\)\s*\{[^}]*box-shadow: none/);
    expect(css).toMatch(/\.map-host\.maplibregl-map\s*\{[^}]*font-family: var\(--font-ui\)/);
    expect(css).toMatch(/background-image: none/);
  });
  it("draws a disclosure marker on filter groups and the raw-rate control (UX-6)", () => {
    expect(css).toMatch(/\.filter-group summary::before/);
    expect(css).toMatch(/\.score-detail summary::before/);
  });
});

describe("pan limits match the tile extract, so the map never goes blank (REQ-WEB-MAP.1)", () => {
  it("keeps the pan limits inside the bounds stored in public/tiles/boston.pmtiles", async () => {
    const { readFileSync } = await import("node:fs");
    const { join } = await import("node:path");
    const { BOSTON_BOUNDS, BOSTON_CENTER, BOSTON_ZOOM, MIN_ZOOM } = await import("./style");
    const head = readFileSync(join(__dirname, "..", "..", "public", "tiles", "boston.pmtiles")).subarray(0, 127);
    expect(head.subarray(0, 7).toString()).toBe("PMTiles");
    const deg = (o: number) => head.readInt32LE(o) / 1e7;
    const [minLon, minLat, maxLon, maxLat] = [deg(102), deg(106), deg(110), deg(114)];
    const [[w, s], [e, n]] = BOSTON_BOUNDS;
    expect(w).toBeGreaterThanOrEqual(minLon - 1e-6);
    expect(s).toBeGreaterThanOrEqual(minLat - 1e-6);
    expect(e).toBeLessThanOrEqual(maxLon + 1e-6);
    expect(n).toBeLessThanOrEqual(maxLat + 1e-6);
    expect(head[101]).toBeGreaterThanOrEqual(13); // full detail where the possible zombies are
    // greater Boston: at least a quarter degree of map on every side of downtown
    expect(BOSTON_CENTER[0] - w).toBeGreaterThan(0.25);
    expect(e - BOSTON_CENTER[0]).toBeGreaterThan(0.25);
    expect(BOSTON_CENTER[1] - s).toBeGreaterThan(0.25);
    expect(n - BOSTON_CENTER[1]).toBeGreaterThan(0.25);
    expect(BOSTON_ZOOM - MIN_ZOOM).toBeGreaterThanOrEqual(1);
    expect(BOSTON_ZOOM - MIN_ZOOM).toBeLessThanOrEqual(2);
  });
});
