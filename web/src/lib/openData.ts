/**
 * Open data download and district report cards (REQ-WEB-OPEN.1-2). Pure functions: the CSV is made in the browser from the
 * same zombies.json the site loads, so a nightly refresh needs no extra build step.
 */
import type { DistrictsFile, Zombie } from "./parse";

export const OPEN_COLUMNS = [
  "zombie_id", "tier", "type_family", "department", "neighborhood", "district", "resurrection_date", "gap_days", "reports_after", "times_risen",
  "coroner_label", "match_mode", "distance_m", "confidence", "confidence_partial", "baseline_p", "skeptic_verdict", "is_planned_followup",
  "after_temporary_fix", "source_unknown", "city_rereport", "bulk_closure", "incident_id", "resurrection_id", "chain_id", "segment_id",
] as const;

const cell = (v: unknown): string => {
  if (v === null || v === undefined) return "";
  const s = typeof v === "string" ? v : String(v);
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

/** CSV text, header first, one row per zombie in the given order, comma separated, CRLF line ends (RFC 4180). */
export function zombiesToCsv(zs: readonly Zombie[]): string {
  const rows = zs.map((z) => OPEN_COLUMNS.map((c) => cell((z as Record<string, unknown>)[c])).join(","));
  return [OPEN_COLUMNS.join(","), ...rows].join("\r\n") + "\r\n";
}

/** Minimal RFC 4180 reader, used by the tests to check that the CSV reads back to the same cells. */
export function parseCsv(text: string): string[][] {
  const out: string[][] = [];
  let row: string[] = [];
  let cur = "";
  let q = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (q) {
      if (ch === '"' && text[i + 1] === '"') { cur += '"'; i++; } else if (ch === '"') q = false; else cur += ch;
    } else if (ch === '"') q = true;
    else if (ch === ",") { row.push(cur); cur = ""; } else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && text[i + 1] === "\n") i++;
      row.push(cur); out.push(row); row = []; cur = "";
    } else cur += ch;
  }
  if (cur !== "" || row.length) { row.push(cur); out.push(row); }
  return out;
}

export interface DistrictSummary {
  district: string;
  count: number;
  byFamily: { family: string; count: number }[];
  byYear: { year: number; count: number }[];
}

/** Headline possible zombies per council district; zombies with no district are left out, never guessed. Districts sort numerically when they are numbers. */
export function districtSummaries(zs: readonly Zombie[]): DistrictSummary[] {
  const by = new Map<string, Zombie[]>();
  for (const z of zs) {
    if (z.tier !== "headline" || !z.district) continue;
    by.set(z.district, [...(by.get(z.district) ?? []), z]);
  }
  const tally = <K extends string | number>(items: Zombie[], key: (z: Zombie) => K | null) => {
    const m = new Map<K, number>();
    for (const z of items) { const k = key(z); if (k !== null) m.set(k, (m.get(k) ?? 0) + 1); }
    return [...m.entries()].sort((a, b) => (typeof a[0] === "number" ? (a[0] as number) - (b[0] as number) : b[1] - a[1] || (a[0] < b[0] ? -1 : 1)));
  };
  return [...by.entries()]
    .map(([district, items]) => ({
      district,
      count: items.length,
      byFamily: tally(items, (z) => z.type_family ?? null).map(([family, count]) => ({ family, count })),
      byYear: tally(items, (z) => (z.resurrection_date ? Number(z.resurrection_date.slice(0, 4)) : null)).map(([year, count]) => ({ year, count })),
    }))
    .sort((a, b) => (Number(a.district) - Number(b.district)) || (a.district < b.district ? -1 : 1));
}

/** The district summaries of `districts.json` in the shape the report cards use (REQ-EXP-SIZE.3): the engine counts them, so the
 * page loads no zombie shard. */
export function districtsFromFile(f: DistrictsFile): DistrictSummary[] {
  return f.districts.map((d) => ({
    district: d.district,
    count: d.count,
    byFamily: d.by_family.map((x) => ({ family: x.family, count: x.count })),
    byYear: d.by_year.map((x) => ({ year: x.year, count: x.count })),
  }));
}
