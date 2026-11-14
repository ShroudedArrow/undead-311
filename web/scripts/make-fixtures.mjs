// REQ-WEB-DATA.3: build FIXTURE files for the web app from data/sample/sample_311.csv until the engine's real exports exist.
// These are NOT detector output. A crude pairing (same family, within 30 m, re-report 1 to 60 days after a closure) stands in
// so every panel has realistic data. Files carry data_version "fixture-..." and follow /schemas. Deterministic: no clock, no RNG.
import { readFileSync, writeFileSync, mkdirSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const csvPath = join(here, "..", "..", "data", "sample", "sample_311.csv");
const outDir = join(here, "..", "public", "data");
const overridePath = join(here, "..", "..", "data", "labels", "judge_tour_override.json");

export function parseCsv(text) {
  const rows = [];
  let row = [], cell = "", q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) {
      if (c === '"' && text[i + 1] === '"') { cell += '"'; i++; }
      else if (c === '"') q = false;
      else cell += c;
    } else if (c === '"') q = true;
    else if (c === ",") { row.push(cell); cell = ""; }
    else if (c === "\n") { row.push(cell); rows.push(row); row = []; cell = ""; }
    else if (c !== "\r") cell += c;
  }
  if (cell || row.length) { row.push(cell); rows.push(row); }
  const head = rows.shift();
  return rows.filter((r) => r.length === head.length).map((r) => Object.fromEntries(head.map((h, i) => [h, r[i]])));
}

const hash = (s) => { let h = 2166136261; for (const ch of s) { h ^= ch.charCodeAt(0); h = Math.imul(h, 16777619); } return (h >>> 0) / 4294967296; };
const R = 6371000;
const dist = (a, b) => {
  const p = Math.PI / 180, dLat = (b.lat - a.lat) * p, dLon = (b.lon - a.lon) * p;
  const x = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * p) * Math.cos(b.lat * p) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(x));
};
const DAY = 86400000;
// UX-1 (ops#14): the stand-in only pairs a re-report that opens at least a day after the closure, never a crew log entry.
const MIN_GAP_DAYS = 1;
const CITY_SOURCES = new Set(["Employee Generated", "City Worker App", "Maximo Integration"]);
const round = (x, n = 3) => Math.round(x * 10 ** n) / 10 ** n;
const cleanText = (s) => (s || "").replace(/&amp;/g, "&").replace(/\s+/g, " ").trim();
const scrubStreet = (s) => cleanText(s).replace(/^INTERSECTION\s+/i, "").replace(/^\d+[A-Za-z-]*\s+/, "") || null;
// UX-11 (ops#24): the two systems spell a few neighborhoods differently; the fixture groups the split ones.
// The engine should normalize this in the export (handoff to:engine); the web app does not guess neighborhood names.
const HOOD_ALIASES = { Allston: "Allston / Brighton", Brighton: "Allston / Brighton" };
const canonicalHood = (h) => (h ? (HOOD_ALIASES[h] ?? h) : null);
const slug = (s) => (s || "unknown").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

function coronerLabel(text, code) {
  const s = (text || "").toLowerCase();
  if (code === "Transitioned") return "referred";
  if (code === "Noted") return "noted";
  if (/duplicate/.test(s)) return "duplicate";
  if (/invalid|no such|not a/.test(s)) return "invalid";
  if (/temporar|patch|made safe|cold patch/.test(s)) return "made_safe_temporary";
  if (/referred|transfer|resubmit/.test(s)) return "referred";
  if (/scheduled|planned|future|capital/.test(s)) return "planned_followup";
  return "resolved";
}

function wilson(k, n) {
  if (n === 0) return { rate: null, lo: null, hi: null, k, n, reason: "no cases" };
  const z = 1.96, p = k / n, d = 1 + (z * z) / n;
  const c = (p + (z * z) / (2 * n)) / d, h = (z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n))) / d;
  return { rate: round(p, 4), lo: round(Math.max(0, c - h), 4), hi: round(Math.min(1, c + h), 4), k, n };
}

/**
 * REQ-STAT-TOUR.1 (UX-10, ops#23): the provisional tour lists the zombies named in data/labels/judge_tour_override.json when that
 * file exists and every ID is in the fixture set (source "override"); otherwise the three headline zombies with the most
 * re-reports, ties by zombie ID (source "most_reports"). Never by confidence score.
 */
export function pickTour(zs, override = null) {
  const ids = new Set(zs.map((z) => z.zombie_id));
  if (Array.isArray(override) && override.length === 3 && override.every((id) => ids.has(id))) return { ids: [...override], source: "override" };
  const pool = zs.filter((z) => z.tier === "headline")
    .sort((x, y) => y.reports_after - x.reports_after || (x.zombie_id < y.zombie_id ? -1 : x.zombie_id > y.zombie_id ? 1 : 0));
  return { ids: pool.slice(0, 3).map((z) => z.zombie_id), source: "most_reports" };
}

/** The owner's override file, or null when it does not exist or is not a list of IDs. Accepts a list or {zombie_ids: [...]}. */
export function readOverride(path = overridePath) {
  try {
    const j = JSON.parse(readFileSync(path, "utf8"));
    const ids = Array.isArray(j) ? j : j?.zombie_ids;
    return Array.isArray(ids) && ids.every((x) => typeof x === "string") ? ids : null;
  } catch { return null; }
}

export function buildFixtures(rows, override = null) {
  const cases = rows
    .map((r) => ({
      id: r.id, system: r.system, open: Date.parse(r.open_time_utc), close: r.close_time_utc ? Date.parse(r.close_time_utc) : null,
      openIso: r.open_time_utc, closeIso: r.close_time_utc || null, status: r.status, text: cleanText(r.closure_text), code: r.closure_code,
      type_raw: r.type_raw, family: r.type_family, dept: r.department || null, hood: canonicalHood(r.neighborhood), street: scrubStreet(r.street),
      lat: Number(r.lat), lon: Number(r.lon), source: r.source,
      cityOriginated: r.system === "legacy" && (CITY_SOURCES.has(r.source) || r.city_originated_type === "true"),
    }))
    .filter((c) => Number.isFinite(c.lat) && Number.isFinite(c.lon) && Number.isFinite(c.open));

  // grid buckets of 0.0005 degrees (about 55 m)
  const key = (c) => `${c.family}|${Math.floor(c.lat / 0.0005)}|${Math.floor(c.lon / 0.0005)}`;
  const grid = new Map();
  for (const c of cases) { const k = key(c); (grid.get(k) ?? grid.set(k, []).get(k)).push(c); }

  const zombies = [], cards = [];
  const seenRe = new Set();
  const closed = cases.filter((c) => c.close !== null).sort((a, b) => a.close - b.close || (a.id < b.id ? -1 : 1));
  for (const a of closed) {
    const label = coronerLabel(a.text, a.code);
    if (label === "duplicate" || label === "invalid") continue;
    let best = null;
    const [f, la, lo] = [a.family, Math.floor(a.lat / 0.0005), Math.floor(a.lon / 0.0005)];
    for (let i = -1; i <= 1; i++) for (let j = -1; j <= 1; j++) {
      for (const b of grid.get(`${f}|${la + i}|${lo + j}`) ?? []) {
        if (b.id === a.id || seenRe.has(b.id) || b.cityOriginated || b.open < a.close + MIN_GAP_DAYS * DAY || b.open > a.close + 60 * DAY) continue;
        const d = dist(a, b);
        if (d > 30) continue;
        if (!best || b.open < best.b.open || (b.open === best.b.open && b.id < best.b.id)) best = { b, d };
      }
    }
    if (!best) continue;
    const { b, d } = best;
    seenRe.add(b.id);
    const gap = (b.open - a.close) / DAY;
    const unknownSource = b.system === "new" && ["made_safe_temporary", "referred", "planned_followup"].includes(label);
    const h = hash(a.id + b.id);
    const tier = unknownSource ? "source_unknown" : h < 0.04 ? "sensitivity" : "headline";
    const incident = `I-${a.id}`;
    const id = `${incident}:${b.id}`;
    const verdict = h > 0.9 ? "weakened" : h > 0.86 ? "explained_away" : h > 0.8 ? "not_reviewed" : "survives";
    const conf = round(Math.max(0.05, Math.min(0.97, 0.75 - gap / 150 - d / 120 + (verdict === "survives" ? 0.1 : -0.1))), 2);
    const bulk = h > 0.97;
    const year = new Date(b.open).getUTCFullYear();
    zombies.push({
      zombie_id: id, incident_id: incident, resurrection_id: b.id, reports_after: 1, gap_days: round(gap, 2), match_mode: "radius",
      distance_m: round(d, 1), tier, baseline_p: round(0.02 + h * 0.2, 3), confidence: conf, confidence_partial: h > 0.93,
      is_planned_followup: false, after_temporary_fix: label === "made_safe_temporary" && b.system === "legacy", source_unknown: unknownSource,
      chain_id: `C-${a.id}`, times_risen: 1, skeptic_verdict: verdict,
      skeptic_notes: verdict === "survives" ? "Fixture note: no objection survived review." : "Fixture note: the closure text is ambiguous about the location.",
      type_family: a.family, department: a.dept, neighborhood: a.hood, district: null, segment_id: null, coroner_label: label,
      bulk_closure: bulk, close_year: new Date(a.close).getUTCFullYear(), resurrection_date: b.openIso.slice(0, 10),
    });
    const rec = (c) => ({ id: c.id, system: c.system, open_time: c.openIso, close_time: c.closeIso, type_raw: c.type_raw, status: c.status, closure_text: c.text || null, street: c.street, lat: c.lat, lon: c.lon });
    cards.push({
      shard: `${slug(a.hood)}-${year}`,
      card: { zombie_id: id, original: rec(a), rereport: rec(b), cause_of_death: label, gap_days: round(gap, 2), resurrection_date: b.openIso.slice(0, 10), confidence: conf, tier, skeptic_verdict: verdict, skeptic_notes: zombies.at(-1).skeptic_notes, reports_after: 1, times_risen: 1, bulk_closure: bulk, confidence_partial: h > 0.93 },
    });
  }

  // keep the fixture small: the 400 highest-confidence pairs, then make sure the kept set exercises the bulk warning and
  // the partial note (REQ-WEB-CARD.1, .6): swap in the best flagged pairs for the lowest-confidence unflagged ones.
  // The cut ignores the gap term of the confidence stand-in, so short and long gaps both survive it (UX-1).
  const cut = (z) => z.confidence + z.gap_days / 150;
  zombies.sort((x, y) => cut(y) - cut(x) || (x.zombie_id < y.zombie_id ? -1 : 1));
  const kept = zombies.slice(0, 400);
  const rest = zombies.slice(400);
  for (const flag of ["bulk_closure", "confidence_partial"]) {
    const want = 8;
    const have = kept.filter((z) => z[flag]).length;
    const extra = rest.filter((z) => z[flag]).slice(0, Math.max(0, want - have));
    for (const z of extra) {
      const victim = kept.findLastIndex((k) => !k.bulk_closure && !k.confidence_partial);
      if (victim >= 0) kept.splice(victim, 1, z);
    }
  }
  const keep = new Set(kept.map((z) => z.zombie_id));
  const zs = zombies.filter((z) => keep.has(z.zombie_id)).sort((x, y) => (x.zombie_id < y.zombie_id ? -1 : 1));
  const byId = new Map(cards.map((c) => [c.card.zombie_id, c]));
  const coords = new Map(cases.map((c) => [c.id, c]));

  const points = { data_version: "", n: zs.length, id: [], lat: [], lon: [], tier: [], family: [], department: [], neighborhood: [], year: [] };
  for (const z of zs) {
    const c = byId.get(z.zombie_id).card.rereport;
    points.id.push(z.zombie_id); points.lat.push(round(c.lat, 6)); points.lon.push(round(c.lon, 6)); points.tier.push(z.tier);
    points.family.push(z.type_family); points.department.push(z.department); points.neighborhood.push(z.neighborhood); points.year.push(Number(z.resurrection_date.slice(0, 4)));
  }

  const shards = new Map();
  for (const z of zs) { const c = byId.get(z.zombie_id); (shards.get(c.shard) ?? shards.set(c.shard, []).get(c.shard)).push(c.card); }

  // scorecards: crude on-time (closed within 30 days) and stayed-fixed (closed on time and not reported again) per family and citywide
  const back = new Set(zombies.map((z) => z.incident_id.slice(2)));
  const fam = new Map();
  for (const c of closed) {
    const e = fam.get(c.family) ?? fam.set(c.family, { n: 0, ontime: 0, stayed: 0 }).get(c.family);
    const ontime = c.close - c.open <= 30 * DAY;
    e.n++; if (ontime) e.ontime++; if (ontime && !back.has(c.id)) e.stayed++;
  }
  const mk = (family, e) => ({
    family, tier_set: "headline", n_closed: e.n, n_on_time_known: e.n, on_time: wilson(e.ontime, e.n),
    stayed_fixed_raw: wilson(e.stayed, e.n),
    // adjusted is a fixture stand-in: a little higher than raw, clamped to the on-time rate (testing.md #17)
    stayed_fixed_adj: wilson(Math.min(e.ontime, Math.round(e.stayed + (e.ontime - e.stayed) * 0.1)), e.n),
  });
  const scorecards = [...fam.entries()].sort((x, y) => (x[0] < y[0] ? -1 : 1)).map(([f, e]) => mk(f, e));
  const total = [...fam.values()].reduce((s, e) => ({ n: s.n + e.n, ontime: s.ontime + e.ontime, stayed: s.stayed + e.stayed }), { n: 0, ontime: 0, stayed: 0 });
  scorecards.unshift(mk("all", total));
  // one family without an adjusted rate, so the raw-only path is exercised
  scorecards.at(-1).stayed_fixed_adj = null;

  const tally = { headline: 0, source_unknown: 0, sensitivity: 0 };
  for (const z of zs) tally[z.tier]++;
  const dataEnd = new Date(Math.max(...cases.map((c) => c.close ?? c.open))).toISOString().slice(0, 10);
  const version = `fixture-${dataEnd}`;
  points.data_version = version;
  const tour = pickTour(zs, override);

  return {
    version,
    files: {
      "zombies.json": { data_version: version, zombies: zs },
      "points.json": points,
      "scorecard.json": { data_version: version, scorecards, counts: tally },
      "status.json": { data_version: version, last_run: `${dataEnd}T02:00:00Z`, ok: true, row_counts: { cases: rows.length, zombies: zs.length }, anomalies: [], segments: "missing", headline_count: tally.headline, source_unknown_count: tally.source_unknown, sensitivity_count: tally.sensitivity, data_end: dataEnd },
      "judge_tour.json": { data_version: version, provisional: true, zombie_ids: tour.ids, source: tour.source },
      "validation.json": { data_version: version, status: "awaiting_field_labels", precision: null, cant_tell_share: null, kappa: null, confirmed: [], sample_ids: [] },
    },
    shards: Object.fromEntries([...shards.entries()].sort().map(([k, v]) => [`cards/${k}.json`, { data_version: version, shard: k, cards: v.sort((x, y) => (x.zombie_id < y.zombie_id ? -1 : 1)) }])),
  };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const { files, shards } = buildFixtures(parseCsv(readFileSync(csvPath, "utf8")), readOverride());
  rmSync(join(outDir, "cards"), { recursive: true, force: true }); // no stale shards when a rule changes
  mkdirSync(join(outDir, "cards"), { recursive: true });
  for (const [name, data] of [...Object.entries(files), ...Object.entries(shards)]) writeFileSync(join(outDir, name), JSON.stringify(data) + "\n");
  console.log(`wrote ${Object.keys(files).length} files and ${Object.keys(shards).length} card shards to ${outDir}`);
}
