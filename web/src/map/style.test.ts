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
