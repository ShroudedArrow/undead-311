/**
 * "Check my street" index and search (REQ-WEB-STREET.1). Plain TypeScript with no Vite imports, so the build script
 * (scripts/make-street-index.ts) uses the same normalization as the browser. No API: the index is one static file.
 */
import { haversineM } from "./geo.ts";

export interface StreetEntry {
  /** Normalized key, the thing searched. */
  k: string;
  /** Name as shown. */
  n: string;
  /** Up to MAX_POINTS [lat, lon] points along the street (5 decimals). */
  p: [number, number][];
}
export interface StreetIndex {
  /** `sam`: built from the SAM address registry. `cases`: built from the streets named in case records (no registry file was available). */
  source: "sam" | "cases";
  streets: StreetEntry[];
}

export const MAX_POINTS = 12;
/** Points kept per street when the index is built from SAM street segments, so a long street keeps a point every few blocks (REQ-WEB-STREET.1). */
export const MAX_POINTS_SAM = 150;

const SUFFIX: Record<string, string> = {
  STREET: "ST", AVENUE: "AVE", ROAD: "RD", BOULEVARD: "BLVD", PLACE: "PL", DRIVE: "DR", LANE: "LN", COURT: "CT", SQUARE: "SQ",
  PARKWAY: "PKWY", TERRACE: "TER", HIGHWAY: "HWY", CIRCLE: "CIR", SAINT: "ST", NORTH: "N", SOUTH: "S", EAST: "E", WEST: "W", MOUNT: "MT",
};

const decode = (s: string): string => s.replace(/&amp;/gi, "&").replace(/&#39;|&apos;/gi, "'");

/** The street names inside a case's address text: "20-22 Radcliffe Rd" gives one, "INTERSECTION A St & B Ave" gives two. */
export function streetsOf(raw: string | null | undefined): string[] {
  if (!raw) return [];
  const text = decode(raw).replace(/^\s*intersection\s+/i, "");
  return text
    .split(/\s+&\s+|\s+\band\b\s+/i)
    .map((part) => part.replace(/^\s*\d+[A-Za-z]?(\s*-\s*\d+[A-Za-z]?)?\s+/, "").replace(/\s+/g, " ").trim())
    .filter((s) => /[A-Za-z]/.test(s));
}

/** Upper-case, punctuation-free key with common suffixes shortened, so "Commonwealth Avenue" and "Commonwealth Ave." match. */
export function normalizeStreet(name: string): string {
  return decode(name)
    .toUpperCase()
    .replace(/[^A-Z0-9' ]+/g, " ")
    .replace(/'/g, "")
    .split(/\s+/)
    .filter(Boolean)
    .map((w) => SUFFIX[w] ?? w)
    .join(" ");
}

const titleCase = (s: string): string => s.replace(/\w\S*/g, (w) => w[0].toUpperCase() + w.slice(1).toLowerCase());

/** Accumulates streets and their points, then writes a compact, deterministic index. */
export class IndexBuilder {
  private map = new Map<string, { n: string; pts: Map<string, [number, number]> }>();
  add(rawName: string, lat: number, lon: number): void {
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
    const key = normalizeStreet(rawName);
    if (!key) return;
    let e = this.map.get(key);
    if (!e) {
      e = { n: titleCase(decode(rawName).trim()), pts: new Map() };
      this.map.set(key, e);
    }
    const p: [number, number] = [Math.round(lat * 1e5) / 1e5, Math.round(lon * 1e5) / 1e5];
    e.pts.set(`${p[0]},${p[1]}`, p);
  }
  build(source: StreetIndex["source"], maxPoints = MAX_POINTS): StreetIndex {
    const streets = [...this.map.entries()]
      .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
      .map(([k, e]) => ({ k, n: e.n, p: spread([...e.pts.values()].sort((a, b) => a[0] - b[0] || a[1] - b[1]), maxPoints) }));
    return { source, streets };
  }
}

/** At most `max` points, evenly spread over the sorted list so a long street keeps points along its length. */
function spread<T>(xs: T[], max: number): T[] {
  if (xs.length <= max) return xs;
  return Array.from({ length: max }, (_, i) => xs[Math.round((i * (xs.length - 1)) / (max - 1))]);
}

/** Search the index: every query word must start a word of the street. Exact, then prefix, then word-prefix matches first. */
export function searchStreets(index: StreetIndex, query: string, limit = 8): StreetEntry[] {
  const q = normalizeStreet(streetsOf(query)[0] ?? query);
  if (!q) return [];
  const words = q.split(" ");
  const scored: { e: StreetEntry; s: number }[] = [];
  for (const e of index.streets) {
    const ew = e.k.split(" ");
    if (!words.every((w, i) => (i === words.length - 1 ? ew.some((x) => x.startsWith(w)) : ew.includes(w) || ew.some((x) => x === w)))) continue;
    scored.push({ e, s: e.k === q ? 0 : e.k.startsWith(q) ? 1 : 2 });
  }
  return scored.sort((a, b) => a.s - b.s || (a.e.k < b.e.k ? -1 : 1)).slice(0, limit).map((x) => x.e);
}

export interface Located {
  id: string;
  lat: number;
  lon: number;
}

/** Items within `radiusM` of any point of the street, nearest first (ties by id), with the distance. */
export function nearStreet<T extends Located>(entry: StreetEntry, items: readonly T[], radiusM: number): { item: T; meters: number }[] {
  const out: { item: T; meters: number }[] = [];
  for (const item of items) {
    let best = Infinity;
    for (const [la, lo] of entry.p) best = Math.min(best, haversineM(la, lo, item.lat, item.lon));
    if (best <= radiusM) out.push({ item, meters: best });
  }
  return out.sort((a, b) => a.meters - b.meters || (a.item.id < b.item.id ? -1 : a.item.id > b.item.id ? 1 : 0));
}

/** Where to zoom: the bounding box of the street's points, as [west, south, east, north]. */
export function boundsOf(entry: StreetEntry): [number, number, number, number] {
  const lats = entry.p.map((p) => p[0]);
  const lons = entry.p.map((p) => p[1]);
  return [Math.min(...lons), Math.min(...lats), Math.max(...lons), Math.max(...lats)];
}

interface SamFeature {
  properties?: { PRE_DIR?: string | null; ST_NAME?: string | null; ST_TYPE?: string | null; SUF_DIR?: string | null } | null;
  geometry?: { type?: string; coordinates?: unknown } | null;
}

/**
 * Read the Analyze Boston SAM street segments GeoJSON (Open Data Commons PDDL) into the builder: one street per name
 * (PRE_DIR, ST_NAME, ST_TYPE, SUF_DIR), with the first, middle and last vertex of every segment as its points.
 * Segments without a name are skipped. Returns the number of segments used (REQ-WEB-STREET.1, UX-45).
 */
export function addFromSamSegments(builder: IndexBuilder, geojson: { features?: SamFeature[] }): number {
  let n = 0;
  for (const f of geojson.features ?? []) {
    const p = f.properties ?? {};
    if (!p.ST_NAME || !/[A-Za-z0-9]/.test(p.ST_NAME)) continue;
    const name = [p.PRE_DIR, p.ST_NAME, p.ST_TYPE, p.SUF_DIR].filter((x): x is string => !!x && x.trim() !== "").join(" ").trim();
    const g = f.geometry;
    if (!name || !g || (g.type !== "LineString" && g.type !== "MultiLineString")) continue;
    const lines = (g.type === "LineString" ? [g.coordinates] : g.coordinates) as [number, number][][];
    const verts = lines.flat().filter((c) => Array.isArray(c) && c.length >= 2);
    if (verts.length === 0) continue;
    for (const [lon, lat] of [verts[0], verts[Math.floor(verts.length / 2)], verts[verts.length - 1]]) builder.add(name, lat, lon);
    n++;
  }
  return n;
}

/** Read a SAM address-registry CSV (one row per address) into the builder. Column names are looked up case-insensitively. */
export function addFromSamCsv(builder: IndexBuilder, csv: string): number {
  const lines = csv.split(/\r?\n/).filter((l) => l.trim());
  if (lines.length < 2) return 0;
  const head = splitCsv(lines[0]).map((h) => h.trim().toLowerCase());
  const col = (...names: string[]) => head.findIndex((h) => names.includes(h));
  const street = col("street_body", "full_street_name", "street_name", "street");
  const lat = col("latitude", "lat", "y");
  const lon = col("longitude", "lon", "long", "x");
  const suffix = col("street_suffix", "suffix");
  if (street < 0 || lat < 0 || lon < 0) throw new Error("SAM CSV needs a street name column (STREET_BODY, FULL_STREET_NAME, STREET_NAME or STREET) and latitude and longitude columns");
  let n = 0;
  for (const line of lines.slice(1)) {
    const c = splitCsv(line);
    const name = [c[street], suffix >= 0 && !(c[street] ?? "").toUpperCase().includes((c[suffix] ?? "").toUpperCase()) ? c[suffix] : ""].filter(Boolean).join(" ").trim();
    if (!name) continue;
    builder.add(name, Number(c[lat]), Number(c[lon]));
    n++;
  }
  return n;
}

function splitCsv(line: string): string[] {
  const out: string[] = [];
  let cur = "";
  let q = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (q) {
      if (ch === '"' && line[i + 1] === '"') { cur += '"'; i++; } else if (ch === '"') q = false; else cur += ch;
    } else if (ch === '"') q = true;
    else if (ch === ",") { out.push(cur); cur = ""; } else cur += ch;
  }
  out.push(cur);
  return out;
}
