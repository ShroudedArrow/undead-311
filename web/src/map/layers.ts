/**
 * Layer stack for the haunted map (REQ-WEB-MAP.1). Pure: builds the deck.gl layers in paint order, bottom to top:
 * bulk rings, the marker hit halo, the stencil markers, the marker hit core, then (below zoom 13 only) spray-dot clusters with their
 * counts and hit circles. Every layer is always present, empty when it has nothing to draw, so the stack never changes shape.
 * There is no neighborhood label layer (owner decision 11, issue 190): the names collided.
 */
import { IconLayer, ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import type { PointRow } from "../lib/points";
import { clusterLabel, clusterSize, groupRows, markerScale, type Cluster } from "./density";
import { clusterIcon, iconFor, iconMapping } from "./sprites";

export interface LayerInput {
  rows: PointRow[];
  selectedId: string | null;
  atlas: HTMLCanvasElement;
  bulkIds: ReadonlySet<string> | null;
  onSelect: (id: string) => void;
  /** Phone-sized screen: smaller markers so neighbours can be told apart and tapped (UX-60). */
  compact?: boolean;
  /** Map zoom. Below the density threshold nearby markers are drawn as clusters, and markers shrink with the zoom. Omitted: full size, no clusters. */
  zoom?: number;
  /** A cluster was clicked or tapped. */
  onCluster?: (c: Cluster) => void;
}

/**
 * Marker size in pixels at full size: 30 (44 when selected), and 26 (38) on a phone, where the stencil letter is still about 9 px tall.
 * Below two zoom steps past the density threshold the unselected markers scale down to 70%; the selected one never shrinks.
 */
export function markerSize(selected: boolean, compact: boolean, zoom: number = Infinity): number {
  const full = compact ? (selected ? 38 : 26) : selected ? 44 : 30;
  return selected ? full : full * markerScale(zoom);
}

/** Smallest touch target: 44 px across, so a hit area on a phone is at least 22 px in radius. */
export const MIN_HIT_RADIUS_PX = 22;

/** Pick radius in pixels of the invisible circle that sits over a marker: the whole painted circle, and on a phone at least 44 px across. */
export function hitRadius(selected: boolean, compact: boolean, zoom: number = Infinity): number {
  const visual = markerSize(selected, compact, zoom) / 2;
  return compact ? Math.max(visual, MIN_HIT_RADIUS_PX) : visual;
}

export function buildLayers(i: LayerInput) {
  const { selectedId, atlas, bulkIds, onSelect } = i;
  const compact = i.compact ?? false;
  const zoom = i.zoom ?? Infinity;
  const onCluster = i.onCluster ?? (() => undefined);
  // below the density threshold, nearby possible zombies become clusters; the selected one is always its own marker
  const { clusters, singles: rows } = groupRows(i.rows, zoom, selectedId);
  const hit = (c: Cluster) => (compact ? Math.max(clusterSize(c.count) / 2, MIN_HIT_RADIUS_PX) : clusterSize(c.count) / 2);
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
      getRadius: (d) => hitRadius(d.id === selectedId, compact, zoom),
      updateTriggers: { getRadius: [selectedId, compact, zoom] },
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
      getSize: (d) => markerSize(d.id === selectedId, compact, zoom),
      sizeUnits: "pixels",
      sizeMinPixels: compact ? 16 : 18,
      updateTriggers: { getSize: [selectedId, compact, zoom] },
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
      getRadius: (d) => markerSize(d.id === selectedId, compact, zoom) / 2,
      updateTriggers: { getRadius: [selectedId, compact, zoom] },
      onClick: (info) => {
        if (info.object) onSelect(info.object.id);
      },
    }),
    // Density view. The count sits on a Crew white badge in Asphalt text (pink is never text); a click or tap on a cluster zooms in on it.
    new IconLayer<Cluster>({
      id: "clusters",
      data: clusters,
      loadOptions: { worker: false },
      iconAtlas: atlas as unknown as string,
      iconMapping: iconMapping(),
      getIcon: (c) => clusterIcon(c.key),
      getPosition: (c) => [c.lon, c.lat],
      getSize: (c) => clusterSize(c.count),
      sizeUnits: "pixels",
    }),
    new TextLayer<Cluster>({
      id: "cluster-count",
      data: clusters,
      getPosition: (c) => [c.lon, c.lat],
      getText: (c) => clusterLabel(c.count),
      getSize: 13,
      sizeUnits: "pixels",
      getColor: [46, 49, 52, 255],
      fontFamily: '"Public Sans", sans-serif',
      fontWeight: 700,
      characterSet: "0123456789k.",
      background: true,
      getBackgroundColor: [244, 244, 239, 255],
      backgroundPadding: [4, 2],
      getTextAnchor: "middle",
      getAlignmentBaseline: "center",
    }),
    new ScatterplotLayer<Cluster>({
      id: "cluster-hit",
      data: clusters,
      pickable: true,
      stroked: false,
      filled: true,
      getFillColor: [0, 0, 0, 0],
      getPosition: (c) => [c.lon, c.lat],
      radiusUnits: "pixels",
      getRadius: hit,
      onClick: (info) => {
        if (info.object) onCluster(info.object);
      },
    }),
  ];
}
