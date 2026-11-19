/**
 * Layer stack for the haunted map (REQ-WEB-MAP.1). Pure: builds the deck.gl layers in paint order, bottom to top:
 * bulk rings, the marker hit halo (phone only), the stencil markers (which are their own hit area), then (below zoom 13 only) spray-dot clusters with their
 * counts and hit circles. Every layer is always present, empty when it has nothing to draw, so the stack never changes shape.
 * The halo only has data on a phone, where a 44 px touch target is wider than the painted circle (REQ-WEB-PERF: one pickable layer).
 * There is no neighborhood label layer (owner decision 11, issue 190): the names collided.
 */
import { IconLayer, ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import type { PointRow } from "../lib/points";
import { clusterLabel, clusterSize, DENSITY_ZOOM, dotScale, groupRows, markerScale, type Cluster, type Grouped } from "./density";
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
  /** The clusters and singles for `zoom`, when the caller has them already (the map keeps them per zoom level). Omitted: worked out here. */
  grouped?: Grouped;
  /** A cluster was clicked or tapped. */
  onCluster?: (c: Cluster) => void;
  /**
   * "density" (the main map): clusters below zoom 13 and markers at 70% to full size. "dots" (the time-lapse): never clusters, and every
   * marker is a small plain spray ring at city zoom (no letter, which would not read at that size), growing to a full stencil circle.
   */
  mode?: MarkerMode;
}

export type MarkerMode = "density" | "dots";

/**
 * Marker size in pixels at full size: 30 (44 when selected), and 26 (38) on a phone, where the stencil letter is still about 9 px tall.
 * Below two zoom steps past the density threshold the unselected markers scale down to 70%; the selected one never shrinks.
 */
export function markerSize(selected: boolean, compact: boolean, zoom: number = Infinity, mode: MarkerMode = "density"): number {
  const full = compact ? (selected ? 38 : 26) : selected ? 44 : 30;
  return selected ? full : full * (mode === "dots" ? dotScale(zoom) : markerScale(zoom));
}

/** Smallest touch target: 44 px across, so a hit area on a phone is at least 22 px in radius. */
export const MIN_HIT_RADIUS_PX = 22;

/** Pick radius in pixels of the invisible circle that sits over a marker: the whole painted circle, and on a phone at least 44 px across. */
export function hitRadius(selected: boolean, compact: boolean, zoom: number = Infinity, mode: MarkerMode = "density"): number {
  const visual = markerSize(selected, compact, zoom, mode) / 2;
  return compact ? Math.max(visual, MIN_HIT_RADIUS_PX) : visual;
}

/** The bulk-ring rows, kept per input so a view change that leaves the rows alone hands deck.gl the same array and nothing is rebuilt. */
const bulkRowCache = new WeakMap<object, WeakMap<object, PointRow[]>>();
function bulkRowsOf(rows: PointRow[], bulkIds: ReadonlySet<string>): PointRow[] {
  let byIds = bulkRowCache.get(rows);
  if (!byIds) bulkRowCache.set(rows, (byIds = new WeakMap()));
  let out = byIds.get(bulkIds);
  if (!out) byIds.set(bulkIds, (out = rows.filter((r) => bulkIds.has(r.id))));
  return out;
}
const NO_ROWS: PointRow[] = [];

/**
 * In the time-lapse the rows grow at the end while it plays. Telling deck.gl that only the new rows changed lets it fill in those
 * rows, not re-run every accessor over every row again each frame. Anything else (a filter, a trail that drops old rows) is a full update.
 */
export function appendOnlyDiff(next: PointRow[], prev: PointRow[]): { startRow: number; endRow: number }[] | null {
  if (prev.length === 0 || next.length <= prev.length) return null;
  for (const at of [0, prev.length >> 1, prev.length - 1]) if (next[at] !== prev[at]) return null;
  return [{ startRow: prev.length, endRow: next.length }];
}

export function buildLayers(i: LayerInput) {
  const { selectedId, atlas, bulkIds, onSelect } = i;
  const compact = i.compact ?? false;
  const zoom = i.zoom ?? Infinity;
  const onCluster = i.onCluster ?? (() => undefined);
  // below the density threshold, nearby possible zombies become clusters; the selected one is always its own marker
  const mode = i.mode ?? "density";
  const { clusters, singles: rows } = i.grouped ?? (mode === "dots" ? { clusters: [] as Cluster[], singles: i.rows } : groupRows(i.rows, zoom, selectedId));
  const diff = mode === "dots" ? { _dataDiff: appendOnlyDiff as never } : {};
  // in dots mode below the density threshold the letter would not read, so the marker is the plain ring
  const plain = mode === "dots" && zoom < DENSITY_ZOOM;
  const hit = (c: Cluster) => (compact ? Math.max(clusterSize(c.count) / 2, MIN_HIT_RADIUS_PX) : clusterSize(c.count) / 2);
  return [
    // Cone orange rings under the markers: a warning, never text (design-system.md). Asphalt ring beneath keeps 3:1 on Concrete.
    ...(bulkIds && bulkIds.size > 0
      ? [
          new ScatterplotLayer<PointRow>({
            id: "bulk-ring-edge", data: bulkRowsOf(rows, bulkIds), getPosition: (d) => [d.lon, d.lat], stroked: true, filled: false,
            radiusUnits: "pixels", getRadius: 22, lineWidthUnits: "pixels", getLineWidth: 8, getLineColor: [46, 49, 52, 255],
          }),
          new ScatterplotLayer<PointRow>({
            id: "bulk-ring", data: bulkRowsOf(rows, bulkIds), getPosition: (d) => [d.lon, d.lat], stroked: true, filled: false,
            radiusUnits: "pixels", getRadius: 22, lineWidthUnits: "pixels", getLineWidth: 4, getLineColor: [242, 107, 29, 255],
          }),
        ]
      : []),
    // The sprite itself is the hit area: alphaCutoff 0 keeps its transparent pixels, so a click anywhere on the marker's square (its
    // empty middle too) picks it, and where markers overlap the one drawn on top wins (deck.gl picks the topmost object; a layer draws
    // in data order). That is one pickable layer instead of an extra invisible circle layer drawn over every marker on every frame.
    // A phone also gets an invisible halo under the sprites: it widens the target to 44 px across but never beats a marker that is
    // visibly under the finger. On a wider screen the halo has no data and costs nothing.
    new ScatterplotLayer<PointRow>({
      id: "zombie-halo",
      data: compact ? rows : NO_ROWS,
      ...diff,
      pickable: true,
      stroked: false,
      filled: true,
      getFillColor: [0, 0, 0, 0],
      getPosition: (d) => [d.lon, d.lat],
      radiusUnits: "pixels",
      getRadius: (d) => hitRadius(d.id === selectedId, compact, zoom, mode),
      updateTriggers: { getRadius: [selectedId, compact, zoom, mode] },
      onClick: (info) => {
        if (info.object) onSelect(info.object.id);
      },
    }),
    new IconLayer<PointRow>({
      id: "zombies",
      data: rows,
      ...diff,
      // never let loaders.gl fetch worker scripts from a CDN (REQ-WEB-PERF.2)
      loadOptions: { worker: false },
      iconAtlas: atlas as unknown as string,
      iconMapping: iconMapping(),
      getIcon: (d) => iconFor(d.id, d.tier, plain ? "" : d.family),
      getPosition: (d) => [d.lon, d.lat],
      getSize: (d) => markerSize(d.id === selectedId, compact, zoom, mode),
      sizeUnits: "pixels",
      sizeMinPixels: mode === "dots" ? 3 : compact ? 16 : 18,
      updateTriggers: { getSize: [selectedId, compact, zoom, mode], getIcon: [plain] },
      pickable: true,
      alphaCutoff: 0,
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
