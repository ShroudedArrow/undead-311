/**
 * Density view for the map (REQ-WEB-MAP.1). At city zoom a thousand stencil circles merge into one pink mass, so below DENSITY_ZOOM
 * nearby possible zombies are grouped into spray-dot clusters with a count, and above it every one is drawn on its own.
 * Pure functions: the layers and the map component call them, and the tests pin them.
 *
 * Grouping uses a fixed grid in world (Web Mercator) pixels, so clusters do not jump while the map is panned. The grid is nested
 * from one whole zoom step to the next, so zooming out never splits a cluster and never shows more items than before.
 *
 * Cost: the rows are indexed once (sorted by id, with their world position at zoom 0), and the clusters are worked out once per whole
 * zoom level and cached, so a zoom or pan between two levels re-queries nothing. Merging clusters whose badges would touch uses a spatial
 * grid and a heap, so it takes about n log n, not n cubed (profile: the old loop was 90% of the main thread at 12,000 points).
 */
import type { PointRow } from "../lib/points";

/** Below this zoom the map shows clusters; at or above it, every possible zombie on its own. */
export const DENSITY_ZOOM = 13;
/** Cluster cell size in screen pixels. A cell holding one possible zombie draws that marker, not a cluster. */
export const CELL_PX = 40;
/**
 * Clusters whose centres end up closer than this on screen are merged, so no count badge covers another (reviewer-ux round 2): a
 * three-digit badge is about 30 px wide, and the spray behind it about 60 px at most.
 */
export const MIN_CLUSTER_GAP_PX = 44;

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

/**
 * Marker size multiplier for the time-lapse, which never clusters (every possible zombie appears on its own): about a third of full size at
 * the opening zoom and less when zoomed out further, so the build-up reads as spray dots gathering rather than one blob, growing to full size at zoom 14.5.
 */
export function dotScale(zoom: number): number {
  if (!Number.isFinite(zoom)) return 1;
  // Zoomed out past the opening view the city shrinks faster than the dots, so they keep shrinking too: 0.15 at the zoom floor (9.2).
  if (zoom < 11) return Math.max(0.15, 0.35 - (11 - zoom) * 0.11);
  return Math.min(1, 0.35 + (zoom - 11) * (0.65 / 3.5));
}

/** Icon size in pixels for a cluster: grows with the log of the count, from about 37 px for 2 to 60 px. */
export function clusterSize(count: number): number {
  return Math.min(60, 30 + 7 * Math.log2(Math.max(2, count)));
}

/** The text on a cluster: the count, or 1.2k from a thousand. */
export function clusterLabel(count: number): string {
  return count < 1000 ? String(count) : `${(count / 1000).toFixed(1)}k`;
}

/** The zoom level the clusters are worked out at: the whole level below the density threshold, and DENSITY_ZOOM (no clusters) from there up. */
export function clusterLevel(zoom: number): number {
  return zoom < DENSITY_ZOOM ? Math.floor(zoom) : DENSITY_ZOOM;
}

const worldX = (lon: number, z: number) => ((lon + 180) / 360) * 512 * 2 ** z;
const worldY = (lat: number, z: number) => {
  const r = (Math.min(85, Math.max(-85, lat)) * Math.PI) / 180;
  return ((1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2) * 512 * 2 ** z;
};

const cmp = (a: string, b: string) => (a < b ? -1 : a > b ? 1 : 0);

interface Draft {
  /** Positions in the id-sorted row list, ascending. */
  members: number[];
  x: number;
  y: number;
  key: string;
  alive: boolean;
}

/** Binary min-heap of candidate merges ordered by distance, then by the two draft keys, so ties break the same way every run. */
class PairHeap {
  private a: { d: number; p: Draft; q: Draft }[] = [];
  private less(i: number, j: number): boolean {
    const x = this.a[i];
    const y = this.a[j];
    if (x.d !== y.d) return x.d < y.d;
    const c = cmp(x.p.key, y.p.key) || cmp(x.q.key, y.q.key);
    return c < 0;
  }
  get size(): number {
    return this.a.length;
  }
  push(d: number, u: Draft, v: Draft): void {
    const [p, q] = u.key < v.key ? [u, v] : [v, u];
    this.a.push({ d, p, q });
    let i = this.a.length - 1;
    while (i > 0) {
      const parent = (i - 1) >> 1;
      if (!this.less(i, parent)) break;
      [this.a[i], this.a[parent]] = [this.a[parent], this.a[i]];
      i = parent;
    }
  }
  pop(): { d: number; p: Draft; q: Draft } | undefined {
    const top = this.a[0];
    const last = this.a.pop();
    if (this.a.length > 0 && last) {
      this.a[0] = last;
      let i = 0;
      for (;;) {
        const l = 2 * i + 1;
        const r = l + 1;
        let m = i;
        if (l < this.a.length && this.less(l, m)) m = l;
        if (r < this.a.length && this.less(r, m)) m = r;
        if (m === i) break;
        [this.a[i], this.a[m]] = [this.a[m], this.a[i]];
        i = m;
      }
    }
    return top;
  }
}

export interface ClusterIndex {
  /** Split the rows into clusters and single markers for a zoom (cached per whole level and kept set). */
  group(zoom: number, keep?: ReadonlySet<string> | string | null, cellPx?: number): Grouped;
}

/** Index rows once. Everything that does not depend on the zoom (id order, world position at zoom 0) is worked out here. */
export function buildClusterIndex(rows: readonly PointRow[]): ClusterIndex {
  const order = rows.map((_, i) => i).sort((a, b) => cmp(rows[a].id, rows[b].id) || a - b); // order[rank] = input position
  const n = rows.length;
  const x0 = new Float64Array(n); // by rank; times 2**z is exact, so these match worldX(lon, z)
  const y0 = new Float64Array(n);
  for (let k = 0; k < n; k++) {
    const r = rows[order[k]];
    x0[k] = worldX(r.lon, 0);
    y0[k] = worldY(r.lat, 0);
  }
  const cache = new Map<string, Grouped>();
  const unclustered: Grouped = { clusters: [], singles: rows as PointRow[] };

  function centre(members: readonly number[], scale: number): { x: number; y: number } {
    let sx = 0;
    let sy = 0;
    for (const m of members) {
      sx += x0[m] * scale;
      sy += y0[m] * scale;
    }
    return { x: sx / members.length, y: sy / members.length };
  }

  function compute(z: number, kept: ReadonlySet<string>, cellPx: number): Grouped {
    const scale = 2 ** z;
    const cells = new Map<string, number[]>();
    for (let k = 0; k < n; k++) {
      if (kept.size > 0 && kept.has(rows[order[k]].id)) continue;
      const key = `${Math.floor((x0[k] * scale) / cellPx)}:${Math.floor((y0[k] * scale) / cellPx)}`;
      const cell = cells.get(key);
      if (cell) cell.push(k);
      else cells.set(key, [k]);
    }
    // cells in key order; each cell with two or more members starts as a cluster
    const drafts: Draft[] = [];
    for (const [key, members] of [...cells.entries()].sort((a, b) => cmp(a[0], b[0]))) {
      if (members.length >= 2) drafts.push({ members, key, alive: true, ...centre(members, scale) });
    }
    // Merge clusters whose centres are closer than the badge gap, closest pair first (ties by key), until none are.
    const gap = MIN_CLUSTER_GAP_PX;
    const grid = new Map<number, Draft[]>();
    const slot = (d: Draft) => Math.floor(d.x / gap) * 4_194_304 + Math.floor(d.y / gap);
    const near = (d: Draft, visit: (o: Draft) => void) => {
      const cx = Math.floor(d.x / gap);
      const cy = Math.floor(d.y / gap);
      for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) for (const o of grid.get((cx + dx) * 4_194_304 + (cy + dy)) ?? []) if (o !== d && o.alive) visit(o);
    };
    const add = (d: Draft) => {
      const k = slot(d);
      const list = grid.get(k);
      if (list) list.push(d);
      else grid.set(k, [d]);
    };
    const heap = new PairHeap();
    for (const d of drafts) add(d);
    for (const d of drafts) near(d, (o) => {
      if (d.key < o.key) {
        const dist = Math.hypot(d.x - o.x, d.y - o.y);
        if (dist < gap) heap.push(dist, d, o);
      }
    });
    let all = drafts;
    while (heap.size > 0) {
      const top = heap.pop()!;
      if (!top.p.alive || !top.q.alive) continue;
      const { p, q } = top;
      p.alive = false;
      q.alive = false;
      const members: number[] = [];
      for (let i = 0, j = 0; i < p.members.length || j < q.members.length; ) {
        if (j >= q.members.length || (i < p.members.length && p.members[i] < q.members[j])) members.push(p.members[i++]);
        else members.push(q.members[j++]);
      }
      const merged: Draft = { members, key: p.key < q.key ? p.key : q.key, alive: true, ...centre(members, scale) };
      all = all === drafts ? [...drafts] : all;
      all.push(merged);
      add(merged);
      near(merged, (o) => {
        const dist = Math.hypot(merged.x - o.x, merged.y - o.y);
        if (dist < gap) heap.push(dist, merged, o);
      });
    }
    const live = all.filter((d) => d.alive).sort((a, b) => cmp(a.key, b.key));
    const clustered = new Uint8Array(n);
    const clusters: Cluster[] = live.map((d) => {
      let lon = 0;
      let lat = 0;
      const ids: string[] = [];
      for (const m of d.members) {
        const r = rows[order[m]];
        lon += r.lon;
        lat += r.lat;
        ids.push(r.id);
        clustered[order[m]] = 1;
      }
      return { key: `${d.key}@${z}`, lon: lon / d.members.length, lat: lat / d.members.length, count: d.members.length, ids };
    });
    return { clusters, singles: rows.filter((_, i) => !clustered[i]) };
  }

  return {
    group(zoom, keep = null, cellPx = CELL_PX) {
      if (!(zoom < DENSITY_ZOOM)) return unclustered;
      const kept: ReadonlySet<string> = typeof keep === "string" ? new Set([keep]) : (keep ?? new Set<string>());
      const z = clusterLevel(zoom);
      const key = `${z}|${cellPx}|${[...kept].sort().join("\u0000")}`;
      const hit = cache.get(key);
      if (hit) return hit;
      const out = compute(z, kept, cellPx);
      if (cache.size >= 6) cache.delete(cache.keys().next().value as string);
      cache.set(key, out);
      return out;
    },
  };
}

const indexes = new WeakMap<readonly PointRow[], ClusterIndex>();

/**
 * Split rows into clusters and single markers for a zoom. At or above DENSITY_ZOOM there are no clusters. A row whose id is in `keep`
 * (the selected marker) is always a single, so an open card never hides inside a cluster. Clusters are worked out per whole zoom level.
 * Results are cached per rows array: pass the same array again and nothing is recomputed.
 */
export function groupRows(rows: readonly PointRow[], zoom: number, keep: ReadonlySet<string> | string | null = null, cellPx: number = CELL_PX): Grouped {
  let index = indexes.get(rows);
  if (!index) {
    index = buildClusterIndex(rows);
    indexes.set(rows, index);
  }
  return index.group(zoom, keep, cellPx);
}
