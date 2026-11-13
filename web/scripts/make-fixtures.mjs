// REQ-WEB-DATA.3: build FIXTURE files for the web app from data/sample/sample_311.csv until the engine's real exports exist.
// These are NOT detector output. A crude pairing (same family, within 30 m, re-report 1 to 60 days after a closure) stands in
// so every panel has realistic data. Files carry data_version "fixture-..." and follow /schemas. Deterministic: no clock, no RNG.
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const csvPath = join(here, "..", "..", "data", "sample", "sample_311.csv");
const outDir = join(here, "..", "public", "data");

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
const round = (x, n = 3) => Math.round(x * 10 ** n) / 10 ** n;
const cleanText = (s) => (s || "").replace(/&amp;/g, "&").replace(/\s+/g, " ").trim();
const scrubStreet = (s) => cleanText(s).replace(/^INTERSECTION\s+/i, "").replace(/^\d+[A-Za-z-]*\s+/, "") || null;
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

export function buildFixtures(rows) {
  const cases = rows
    .map((r) => ({
      id: r.id, system: r.system, open: Date.parse(r.open_time_utc), close: r.close_time_utc ? Date.parse(r.close_time_utc) : null,
      openIso: r.open_time_utc, closeIso: r.close_time_utc || null, status: r.status, text: cleanText(r.closure_text), code: r.closure_code,
      type_raw: r.type_raw, family: r.type_family, dept: r.department || null, hood: r.neighborhood || null, street: scrubStreet(r.street),
      lat: Number(r.lat), lon: Number(r.lon), source: r.source,
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
        if (b.id === a.id || seenRe.has(b.id) || b.open <= a.close || b.open > a.close + 60 * DAY) continue;
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
      card: { zombie_id: id, original: rec(a), rereport: rec(b), cause_of_death: label, gap_days: round(gap, 2), resurrection_date: b.openIso.slice(0, 10), confidence: conf, tier, skeptic_verdict: verdict, skeptic_notes: zombies.at(-1).skeptic_notes, reports_after: 1, times_risen: 1, bulk_closure: bulk },
    });
  }

  // keep the fixture small: the 400 highest-confidence pairs, plus any ids needed for the tour
  zombies.sort((x, y) => y.confidence - x.confidence || (x.zombie_id < y.zombie_id ? -1 : 1));
  const keep = new Set(zombies.slice(0, 400).map((z) => z.zombie_id));
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

  // scorecards: crude on-time (closed within 30 days) and stayed-fixed (no pair found) per family and citywide
  const fam = new Map();
  for (const c of closed) {
    const e = fam.get(c.family) ?? fam.set(c.family, { n: 0, ontime: 0, back: 0 }).get(c.family);
    e.n++; if (c.close - c.open <= 30 * DAY) e.ontime++;
  }
  for (const z of zombies) { const e = fam.get(z.type_family); if (e) e.back++; }
  const mk = (family, e) => ({
    family, tier_set: "headline", n_closed: e.n, n_on_time_known: e.n, on_time: wilson(e.ontime, e.n),
    stayed_fixed_raw: wilson(Math.max(0, e.n - e.back), e.n), stayed_fixed_adj: wilson(Math.max(0, e.n - e.back), e.n),
  });
  const scorecards = [...fam.entries()].sort((x, y) => (x[0] < y[0] ? -1 : 1)).map(([f, e]) => mk(f, e));
  const total = [...fam.values()].reduce((s, e) => ({ n: s.n + e.n, ontime: s.ontime + e.ontime, back: s.back + e.back }), { n: 0, ontime: 0, back: 0 });
  scorecards.unshift(mk("all", total));
  // one family without an adjusted rate, so the raw-only path is exercised
  const last = scorecards.at(-1); last.stayed_fixed_adj = null;

  const tally = { headline: 0, source_unknown: 0, sensitivity: 0 };
  for (const z of zs) tally[z.tier]++;
  const dataEnd = new Date(Math.max(...cases.map((c) => c.close ?? c.open))).toISOString().slice(0, 10);
  const version = `fixture-${dataEnd}`;
  points.data_version = version;
  const top = [...zs].sort((x, y) => y.confidence - x.confidence).filter((z) => z.tier === "headline").slice(0, 3).map((z) => z.zombie_id);

  return {
    version,
    files: {
      "zombies.json": { data_version: version, zombies: zs },
      "points.json": points,
      "scorecard.json": { data_version: version, scorecards, counts: tally },
      "status.json": { data_version: version, last_run: `${dataEnd}T02:00:00Z`, ok: true, row_counts: { cases: rows.length, zombies: zs.length }, anomalies: [], segments: "missing", headline_count: tally.headline, source_unknown_count: tally.source_unknown, sensitivity_count: tally.sensitivity, data_end: dataEnd },
      "judge_tour.json": { data_version: version, provisional: true, zombie_ids: top, source: "most_reports" },
      "validation.json": { data_version: version, status: "awaiting_field_labels", precision: null, cant_tell_share: null, kappa: null, confirmed: [], sample_ids: [] },
    },
    shards: Object.fromEntries([...shards.entries()].sort().map(([k, v]) => [`cards/${k}.json`, { data_version: version, shard: k, cards: v.sort((x, y) => (x.zombie_id < y.zombie_id ? -1 : 1)) }])),
  };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const { files, shards } = buildFixtures(parseCsv(readFileSync(csvPath, "utf8")));
  mkdirSync(join(outDir, "cards"), { recursive: true });
  for (const [name, data] of [...Object.entries(files), ...Object.entries(shards)]) writeFileSync(join(outDir, name), JSON.stringify(data) + "\n");
  console.log(`wrote ${Object.keys(files).length} files and ${Object.keys(shards).length} card shards to ${outDir}`);
}
