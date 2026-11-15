// REQ-WEB-STREET.1: build the "Check my street" index at build time (no API at runtime).
// Source, in order (owner decision, ops#170: the Analyze Boston SAM registry, ODC-PDDL):
//   1. SAM_SEGMENTS_GEOJSON: a local SAM street segments GeoJSON file (the pipeline's raw/street_segments_sam.geojson works);
//   2. the SAM street segments GeoJSON downloaded from data.boston.gov through CKAN (skipped when SAM_DOWNLOAD=skip);
//   3. the index already committed at src/generated/streets.json, when it was built from SAM (the build then never loses it);
//   4. SAM_ADDRESSES_CSV, an address registry CSV (street name, latitude and longitude columns);
//   5. the streets named in the card shards under public/data/cards (source "cases", shown with a note on the page).
// The download is read at build time only; the site ships the small index file and makes no outside request when it runs.
// Usage: node scripts/make-street-index.ts            (writes src/generated/streets.json)
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { addFromSamCsv, addFromSamSegments, IndexBuilder, MAX_POINTS_SAM, streetsOf, type StreetIndex } from "../src/lib/streets.ts";

const here = dirname(fileURLToPath(import.meta.url));
const cards = join(here, "..", "public", "data", "cards");
const target = join(here, "..", "src", "generated", "streets.json");
const PACKAGE = "https://data.boston.gov/api/3/action/package_show?id=boston-street-segments-sam-system";
const builder = new IndexBuilder();
let index: StreetIndex | null = null;

/** The SAM segments GeoJSON text from a local file or the open data portal, or null (with a notice) when neither works. */
async function samSegments(): Promise<string | null> {
  const local = process.env.SAM_SEGMENTS_GEOJSON;
  if (local) {
    if (existsSync(local)) return readFileSync(local, "utf8");
    console.warn(`make-street-index: SAM_SEGMENTS_GEOJSON=${local} does not exist`);
  }
  if (process.env.SAM_DOWNLOAD === "skip") return null;
  try {
    const pkg = (await (await fetch(PACKAGE, { signal: AbortSignal.timeout(60_000) })).json()) as { result: { resources: { format?: string; url: string }[] } };
    const res = pkg.result.resources.find((r) => (r.format ?? "").toUpperCase() === "GEOJSON");
    if (!res) throw new Error("the package lists no GeoJSON resource");
    const r = await fetch(res.url, { signal: AbortSignal.timeout(180_000) });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return await r.text();
  } catch (e) {
    console.warn(`make-street-index: the SAM download failed (${e instanceof Error ? e.message : "unknown"})`);
    return null;
  }
}

const geojson = await samSegments();
if (geojson) {
  const n = addFromSamSegments(builder, JSON.parse(geojson));
  console.log(`make-street-index: ${n} SAM street segments`);
  index = builder.build("sam", MAX_POINTS_SAM);
}
if (!index && existsSync(target)) {
  const kept = JSON.parse(readFileSync(target, "utf8")) as StreetIndex;
  if (kept.source === "sam") {
    console.warn("make-street-index: keeping the SAM index already in src/generated/streets.json");
    index = kept;
  }
}
const csv = process.env.SAM_ADDRESSES_CSV;
if (!index && csv && existsSync(csv)) {
  console.log(`make-street-index: ${addFromSamCsv(builder, readFileSync(csv, "utf8"))} SAM address rows`);
  index = builder.build("sam");
}
if (!index) {
  console.warn("make-street-index: no SAM file; using the streets in case records");
  for (const f of existsSync(cards) ? readdirSync(cards).filter((x) => x.endsWith(".json")).sort() : []) {
    const shard = JSON.parse(readFileSync(join(cards, f), "utf8")) as { cards?: { original: { street?: string | null; lat: number; lon: number }; rereport: { street?: string | null; lat: number; lon: number } }[] };
    for (const c of shard.cards ?? []) for (const r of [c.original, c.rereport]) for (const s of streetsOf(r.street)) builder.add(s, r.lat, r.lon);
  }
  index = builder.build("cases");
}
mkdirSync(dirname(target), { recursive: true });
writeFileSync(target, JSON.stringify(index) + "\n");
console.log(`make-street-index: ${index.streets.length} streets (${index.source}) -> src/generated/streets.json`);
