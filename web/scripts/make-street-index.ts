// REQ-WEB-STREET.1: build the "Check my street" index at build time (no API at runtime).
// Source: the SAM address registry CSV when SAM_ADDRESSES_CSV points at one (street name, latitude and longitude columns);
// otherwise the streets named in the card shards under public/data/cards (source "cases").
// Usage: node scripts/make-street-index.ts            (writes src/generated/streets.json)
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { addFromSamCsv, IndexBuilder, streetsOf } from "../src/lib/streets.ts";

const here = dirname(fileURLToPath(import.meta.url));
const cards = join(here, "..", "public", "data", "cards");
const target = join(here, "..", "src", "generated", "streets.json");
const builder = new IndexBuilder();
const sam = process.env.SAM_ADDRESSES_CSV;
let source: "sam" | "cases" = "cases";

if (sam && existsSync(sam)) {
  const n = addFromSamCsv(builder, readFileSync(sam, "utf8"));
  source = "sam";
  console.log(`make-street-index: ${n} SAM address rows`);
} else {
  if (sam) console.warn(`make-street-index: SAM_ADDRESSES_CSV=${sam} does not exist; using the streets in case records`);
  for (const f of existsSync(cards) ? readdirSync(cards).filter((x) => x.endsWith(".json")).sort() : []) {
    const shard = JSON.parse(readFileSync(join(cards, f), "utf8")) as { cards?: { original: { street?: string | null; lat: number; lon: number }; rereport: { street?: string | null; lat: number; lon: number } }[] };
    for (const c of shard.cards ?? []) for (const r of [c.original, c.rereport]) for (const s of streetsOf(r.street)) builder.add(s, r.lat, r.lon);
  }
}
const index = builder.build(source);
mkdirSync(dirname(target), { recursive: true });
writeFileSync(target, JSON.stringify(index) + "\n");
console.log(`make-street-index: ${index.streets.length} streets (${source}) -> src/generated/streets.json`);
