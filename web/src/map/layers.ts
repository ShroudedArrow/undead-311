/**
 * Layer stack for the haunted map (REQ-WEB-MAP.1). Pure: builds the deck.gl layers in paint order, bottom to top:
 * bulk rings, zombie markers. There is no neighborhood label layer (owner decision 11, issue 190): the names collided.
 */
import { IconLayer, ScatterplotLayer } from "@deck.gl/layers";
import type { PointRow } from "../lib/points";
import { iconFor, iconMapping } from "./sprites";

export interface LayerInput {
  rows: PointRow[];
  selectedId: string | null;
  atlas: HTMLCanvasElement;
  bulkIds: ReadonlySet<string> | null;
  onSelect: (id: string) => void;
  /** Phone-sized screen: smaller markers so neighbours can be told apart and tapped (UX-60). */
  compact?: boolean;
}

/** Marker size in pixels: 30 (44 when selected), and 26 (38) on a phone, where the stencil letter is still about 9 px tall. */
export function markerSize(selected: boolean, compact: boolean): number {
  return compact ? (selected ? 38 : 26) : selected ? 44 : 30;
}

/** Smallest touch target: 44 px across, so a hit area on a phone is at least 22 px in radius. */
export const MIN_HIT_RADIUS_PX = 22;

/** Pick radius in pixels of the invisible circle that sits over a marker: the whole painted circle, and on a phone at least 44 px across. */
export function hitRadius(selected: boolean, compact: boolean): number {
  const visual = markerSize(selected, compact) / 2;
  return compact ? Math.max(visual, MIN_HIT_RADIUS_PX) : visual;
}

export function buildLayers(i: LayerInput) {
  const { rows, selectedId, atlas, bulkIds, onSelect } = i;
  const compact = i.compact ?? false;
  return [
    // Cone orange rings under the markers: a warning, never text (design-system.md). Asphalt ring beneath keeps 3:1 on Concrete.
    ...(bulkIds && bulkIds.size > 0
      ? [
          new ScatterplotLayer<PointRow>({
            id: "bulk-ring-edge", data: rows.filter((r) => bulkIds.has(r.id)), getPosition: (d) => [d.lon, d.lat], stroked: true, filled: false,
            radiusUnits: "pixels", getRadius: 22, lineWidthUnits: "pixels", getLineWidth: 8, getLineColor: [46, 49, 52, 255],
          }),
          new ScatterplotLayer<PointRow>({
            id: "bulk-ring", data: rows.filter((r) => bulkIds.has(r.id)), getPosition: (d) => [d.lon, d.lat], stroked: true, filled: false,
            radiusUnits: "pixels", getRadius: 22, lineWidthUnits: "pixels", getLineWidth: 4, getLineColor: [242, 107, 29, 255],
          }),
        ]
      : []),
    // Transparent pixels are not pickable, so a click on a marker's empty middle would miss the sprite. Two invisible circles fix that,
    // and neither changes what is drawn. The halo lies under the sprites: it widens the target (44 px across on a phone) but never
    // beats a marker that is visibly under the pointer. The core lies over them at the painted size: it covers the whole circle, and
    // where markers overlap, the one drawn last (on top) wins, because deck.gl picks the topmost object and a layer draws in data order.
    new ScatterplotLayer<PointRow>({
      id: "zombie-halo",
      data: rows,
      pickable: true,
      stroked: false,
      filled: true,
      getFillColor: [0, 0, 0, 0],
      getPosition: (d) => [d.lon, d.lat],
      radiusUnits: "pixels",
      getRadius: (d) => hitRadius(d.id === selectedId, compact),
      updateTriggers: { getRadius: [selectedId, compact] },
      onClick: (info) => {
        if (info.object) onSelect(info.object.id);
      },
    }),
    new IconLayer<PointRow>({
      id: "zombies",
      data: rows,
      // never let loaders.gl fetch worker scripts from a CDN (REQ-WEB-PERF.2)
      loadOptions: { worker: false },
      iconAtlas: atlas as unknown as string,
      iconMapping: iconMapping(),
      getIcon: (d) => iconFor(d.id, d.tier, d.family),
      getPosition: (d) => [d.lon, d.lat],
      getSize: (d) => markerSize(d.id === selectedId, compact),
      sizeUnits: "pixels",
      sizeMinPixels: compact ? 16 : 18,
      updateTriggers: { getSize: [selectedId, compact] },
    }),
    new ScatterplotLayer<PointRow>({
      id: "zombie-hit",
      data: rows,
      pickable: true,
      stroked: false,
      filled: true,
      getFillColor: [0, 0, 0, 0],
      getPosition: (d) => [d.lon, d.lat],
      radiusUnits: "pixels",
      getRadius: (d) => markerSize(d.id === selectedId, compact) / 2,
      updateTriggers: { getRadius: [selectedId, compact] },
      onClick: (info) => {
        if (info.object) onSelect(info.object.id);
      },
    }),
  ];
}
