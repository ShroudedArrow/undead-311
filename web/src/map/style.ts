/**
 * Map style restyled by hand to the palette (REQ-WEB-MAP.1, design-system.md): Concrete land, water and buildings (Asphalt
 * edges), Asphalt streets. Crew white stays free for the city's closed marks. No default dark basemap, no labels (glyph files are not self-hosted yet; see the PR notes).
 * Layers follow the Protomaps basemap schema of the self-hosted extract in public/tiles/boston.pmtiles.
 */
import type { StyleSpecification } from "maplibre-gl";
import { PALETTE } from "./palette";

export const BOSTON_CENTER: [number, number] = [-71.075, 42.325];
export const BOSTON_ZOOM = 11.2;
/**
 * Pan limits: greater Boston (the Route 128 ring) plus a margin. They equal the bounds of the self-hosted tile extract
 * (web/scripts/make-basemap.sh), so the view can never leave the area the tiles draw; a test reads the file's header to keep the two equal.
 */
export const BOSTON_BOUNDS: [[number, number], [number, number]] = [
  [-71.55, 42.05],
  [-70.65, 42.65],
];
/** Lowest zoom: two steps out from the opening view. On a wide screen the pan limits stop the zoom-out a little earlier (about 9.6). */
export const MIN_ZOOM = BOSTON_ZOOM - 2;

export function tilesUrl(origin: string, baseUrl: string): string {
  return `pmtiles://${origin}${baseUrl}tiles/boston.pmtiles`;
}

export function buildStyle(tiles: string, attribution: string): StyleSpecification {
  // Hierarchy by weight and tint, so the pink marks read first: a lighter Asphalt tint on the small streets, full Asphalt on the arterials.
  const road = (id: string, kinds: string[], width: [number, number, number, number], minzoom = 0, opacity = 1) => ({
    id,
    type: "line" as const,
    source: "boston",
    "source-layer": "roads",
    minzoom,
    filter: ["in", ["get", "kind"], ["literal", kinds]] as never,
    layout: { "line-cap": "butt" as const, "line-join": "round" as const },
    paint: {
      "line-color": PALETTE.asphalt,
      "line-opacity": opacity,
      "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 8, width[0], 12, width[1], 15, width[2], 18, width[3]] as never,
    },
  });
  return {
    version: 8,
    sources: { boston: { type: "vector", url: tiles, attribution } },
    layers: [
      { id: "land", type: "background", paint: { "background-color": PALETTE.concrete } },
      // UX-3 (ops#16): Crew white is reserved for the city's closed marks, so water and buildings are Concrete with an Asphalt edge.
      { id: "water", type: "fill", source: "boston", "source-layer": "water", paint: { "fill-color": PALETTE.concrete } },
      {
        id: "water-edge",
        type: "line",
        source: "boston",
        "source-layer": "water",
        paint: { "line-color": PALETTE.asphalt, "line-width": 1.2, "line-opacity": 0.7 },
      },
      {
        id: "buildings",
        type: "fill",
        source: "boston",
        "source-layer": "buildings",
        minzoom: 14,
        paint: { "fill-color": PALETTE.concrete, "fill-outline-color": PALETTE.asphalt },
      },
      road("roads-minor", ["minor_road", "other"], [0.1, 0.4, 1, 3], 12.5, 0.6),
      road("roads-medium", ["medium_road"], [0.2, 0.7, 1.8, 5], 0, 0.5),
      road("roads-major", ["major_road"], [0.4, 1.1, 2.6, 8]),
      road("roads-highway", ["highway"], [0.8, 1.6, 3.4, 10]),
    ],
  };
}
