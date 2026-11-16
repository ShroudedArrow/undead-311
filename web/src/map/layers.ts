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

/** Marker size in pixels: 30 (44 when selected), and 20 (36) on a phone. */
export function markerSize(selected: boolean, compact: boolean): number {
  return compact ? (selected ? 36 : 20) : selected ? 44 : 30;
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
    new IconLayer<PointRow>({
      id: "zombies",
      data: rows,
      pickable: true,
      // never let loaders.gl fetch worker scripts from a CDN (REQ-WEB-PERF.2)
      loadOptions: { worker: false },
      iconAtlas: atlas as unknown as string,
      iconMapping: iconMapping(),
      getIcon: (d) => iconFor(d.id, d.tier),
      getPosition: (d) => [d.lon, d.lat],
      getSize: (d) => markerSize(d.id === selectedId, compact),
      sizeUnits: "pixels",
      sizeMinPixels: compact ? 12 : 14,
      updateTriggers: { getSize: [selectedId, compact] },
      onClick: (info) => {
        if (info.object) onSelect(info.object.id);
      },
    }),
  ];
}
