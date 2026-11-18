/**
 * Density view for the map (REQ-WEB-MAP.1). At city zoom a thousand stencil circles merge into one pink mass, so below DENSITY_ZOOM
 * nearby possible zombies are grouped into spray-dot clusters with a count, and above it every one is drawn on its own.
 * Pure functions: the layers and the map component call them, and the tests pin them.
 *
 * Grouping uses a fixed grid in world (Web Mercator) pixels, so clusters do not jump while the map is panned. The grid is nested
 * from one whole zoom step to the next, so zooming out never splits a cluster and never shows more items than before.
 */
import type { PointRow } from "../lib/points";

/** Below this zoom the map shows clusters; at or above it, every possible zombie on its own. */
export const DENSITY_ZOOM = 13;
/** Cluster cell size in screen pixels. A cell holding one possible zombie draws that marker, not a cluster. */
export const CELL_PX = 40;

export interface Cluster {
  /** Stable id: the grid cell, for example "3:5@11". */
  key: string;
  lon: number;
  lat: number;
  count: number;
  /** Member ids, sorted. */
  ids: string[];
}

export interface Grouped {
  clusters: Cluster[];
  /** Rows to draw as individual markers, in the order they were given. */
  singles: PointRow[];
}

/** Marker size multiplier: 0.7 at the density threshold, growing to 1 two zoom steps in. Markers shrink as the map zooms out, so they merge later. */
export function markerScale(zoom: number): number {
  if (!Number.isFinite(zoom)) return 1;
  return Math.min(1, Math.max(0.7, 0.7 + (zoom - DENSITY_ZOOM) * 0.15));
}

/** Icon size in pixels for a cluster: grows with the log of the count, from about 37 px for 2 to 60 px. */
export function clusterSize(count: number): number {
  return Math.min(60, 30 + 7 * Math.log2(Math.max(2, count)));
}

/** The text on a cluster: the count, or 1.2k from a thousand. */
export function clusterLabel(count: number): string {
  return count < 1000 ? String(count) : `${(count / 1000).toFixed(1)}k`;
}

const worldX = (lon: number, z: number) => ((lon + 180) / 360) * 512 * 2 ** z;
const worldY = (lat: number, z: number) => {
  const r = (Math.min(85, Math.max(-85, lat)) * Math.PI) / 180;
  return ((1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2) * 512 * 2 ** z;
};

/**
 * Split rows into clusters and single markers for a zoom. At or above DENSITY_ZOOM there are no clusters. A row whose id is in `keep`
 * (the selected marker) is always a single, so an open card never hides inside a cluster.
 */
export function groupRows(rows: readonly PointRow[], zoom: number, keep: ReadonlySet<string> | string | null = null, cellPx: number = CELL_PX): Grouped {
  if (!(zoom < DENSITY_ZOOM)) return { clusters: [], singles: [...rows] };
  const z = Math.floor(zoom * 2) / 2; // a half step at a time, so clusters do not flicker while a pinch is in progress
  const kept = typeof keep === "string" ? new Set([keep]) : (keep ?? new Set<string>());
  const cells = new Map<string, PointRow[]>();
  for (const r of rows) {
    if (kept.has(r.id)) continue;
    const key = `${Math.floor(worldX(r.lon, z) / cellPx)}:${Math.floor(worldY(r.lat, z) / cellPx)}`;
    const cell = cells.get(key);
    if (cell) cell.push(r);
    else cells.set(key, [r]);
  }
  const clusters: Cluster[] = [];
  const single = new Set<string>();
  for (const [key, members] of [...cells.entries()].sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0))) {
    if (members.length === 1) {
      single.add(members[0].id);
      continue;
    }
    const sorted = [...members].sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0)); // so the centre does not depend on input order
    clusters.push({
      key: `${key}@${z}`,
      lon: sorted.reduce((s, r) => s + r.lon, 0) / sorted.length,
      lat: sorted.reduce((s, r) => s + r.lat, 0) / sorted.length,
      count: sorted.length,
      ids: sorted.map((r) => r.id),
    });
  }
  const inCluster = new Set(clusters.flatMap((c) => c.ids));
  return { clusters, singles: rows.filter((r) => !inCluster.has(r.id)) };
}
