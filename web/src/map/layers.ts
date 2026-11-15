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
}

export function buildLayers(i: LayerInput) {
  const { rows, selectedId, atlas, bulkIds, onSelect } = i;
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
      getSize: (d) => (d.id === selectedId ? 44 : 30),
      sizeUnits: "pixels",
      sizeMinPixels: 14,
      updateTriggers: { getSize: [selectedId] },
      onClick: (info) => {
        if (info.object) onSelect(info.object.id);
      },
    }),
  ];
}
