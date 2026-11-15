/**
 * Layer stack for the haunted map (REQ-WEB-MAP.1, ops#18, UX-47). Pure: builds the deck.gl layers in paint order.
 * Order, bottom to top: bulk rings, zombie markers, neighborhood labels. The labels go last so a spray circle never
 * paints over a name where possible zombies cluster; they are not pickable, so a click still reaches the marker.
 */
import { IconLayer, ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import type { PlaceLabel } from "../lib/placeLabels";
import type { PointRow } from "../lib/points";
import { iconFor, iconMapping } from "./sprites";

export interface LayerInput {
  rows: PointRow[];
  selectedId: string | null;
  atlas: HTMLCanvasElement;
  bulkIds: ReadonlySet<string> | null;
  labels: readonly PlaceLabel[];
  /** False until the self-hosted Public Sans has loaded, so labels are never drawn in a fallback face. */
  fontReady: boolean;
  onSelect: (id: string) => void;
}

export function buildLayers(i: LayerInput) {
  const { rows, selectedId, atlas, bulkIds, labels, fontReady, onSelect } = i;
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
    // Last, so names stay readable over the pink circles. The Concrete halo keeps them readable on the marker colour.
    ...(fontReady && labels.length > 0
      ? [
          new TextLayer<PlaceLabel>({
            id: "place-labels", data: labels as PlaceLabel[], pickable: false, getPosition: (d) => [d.lon, d.lat], getText: (d) => d.name,
            getSize: 14, sizeUnits: "pixels", fontFamily: '"Public Sans", system-ui, sans-serif', fontWeight: 600, fontSettings: { sdf: true },
            getColor: [46, 49, 52, 255], outlineWidth: 3, outlineColor: [205, 203, 198, 255], getTextAnchor: "middle", getAlignmentBaseline: "center",
            characterSet: "auto",
          }),
        ]
      : []),
  ];
}
