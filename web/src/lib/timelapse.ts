/**
 * "Night of the Living 311" time-lapse logic (REQ-WEB-TIMELAPSE.1). Pure functions: the page owns the clock.
 * Each possible zombie appears on the day it was reported again, and stays on the map.
 */
import type { PointRow } from "./points";

export interface Dated {
  row: PointRow;
  /** Day the possible zombie was reported again, as milliseconds since the epoch (UTC midnight). */
  t: number;
}

export const DAY_MS = 86_400_000;
/** Length of the animation in seconds (the page may shorten it for a short span). */
export const DURATION_S = 24;

/** Join headline points to their re-report dates; points with no valid date are left out. Sorted by time, then ID. */
export function buildTimeline(rows: readonly PointRow[], dateById: ReadonlyMap<string, string>): Dated[] {
  const out: Dated[] = [];
  for (const row of rows) {
    if (row.tier !== "headline") continue;
    const d = dateById.get(row.id);
    const t = d ? Date.parse(d.length === 10 ? `${d}T00:00:00Z` : d) : NaN;
    if (Number.isFinite(t)) out.push({ row, t: Math.floor(t / DAY_MS) * DAY_MS });
  }
  return out.sort((a, b) => a.t - b.t || (a.row.id < b.row.id ? -1 : a.row.id > b.row.id ? 1 : 0));
}

/** Number of dated items at or before time `t` (binary search; the timeline is sorted). */
export function countAt(timeline: readonly Dated[], t: number): number {
  let lo = 0;
  let hi = timeline.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (timeline[mid].t <= t) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

/** The rows visible at time `t`. */
export function visibleAt(timeline: readonly Dated[], t: number): PointRow[] {
  return timeline.slice(0, countAt(timeline, t)).map((d) => d.row);
}

/** Time at a progress between 0 and 1 across the span (clamped). */
export function timeAt(start: number, end: number, progress: number): number {
  const p = Math.min(1, Math.max(0, Number.isFinite(progress) ? progress : 0));
  return start + Math.round((end - start) * p);
}

/** Possible zombies per year, for the static summary shown instead of the animation (also useful beside it). */
export function yearCounts(timeline: readonly Dated[]): { year: number; count: number; total: number }[] {
  const by = new Map<number, number>();
  for (const d of timeline) {
    const y = new Date(d.t).getUTCFullYear();
    by.set(y, (by.get(y) ?? 0) + 1);
  }
  let total = 0;
  return [...by.entries()].sort((a, b) => a[0] - b[0]).map(([year, count]) => ({ year, count, total: (total += count) }));
}

/** Playback speeds offered on the page; 1 is the pace the page had before the control existed. */
export const SPEEDS = [0.5, 1, 2, 4] as const;
/** Trail lengths in months. `null` (not listed) means everything so far. */
export const TRAIL_MONTHS = [3, 6, 12, 24] as const;

export interface Focus {
  /** A type family key, or null for all. */
  family: string | null;
  /** A neighborhood name, or null for all. */
  neighborhood: string | null;
  /** First and last year (inclusive) of the day reported again, or null for no limit. */
  fromYear: number | null;
  toYear: number | null;
}

export const NO_FOCUS: Focus = { family: null, neighborhood: null, fromYear: null, toYear: null };

/** Keep the dated items inside the focus. Order is kept, so the result is still sorted. */
export function focusTimeline(timeline: readonly Dated[], f: Focus): Dated[] {
  return timeline.filter((d) => {
    if (f.family !== null && d.row.family !== f.family) return false;
    if (f.neighborhood !== null && (d.row.neighborhood ?? "") !== f.neighborhood) return false;
    const y = new Date(d.t).getUTCFullYear();
    if (f.fromYear !== null && y < f.fromYear) return false;
    if (f.toYear !== null && y > f.toYear) return false;
    return true;
  });
}

/** The time `months` calendar months before `t` (UTC; the day is clamped to the length of that month). */
export function monthsBefore(t: number, months: number): number {
  const d = new Date(t);
  const first = Date.UTC(d.getUTCFullYear(), d.getUTCMonth() - months, 1);
  const len = new Date(Date.UTC(new Date(first).getUTCFullYear(), new Date(first).getUTCMonth() + 1, 0)).getUTCDate();
  return first + (Math.min(d.getUTCDate(), len) - 1) * DAY_MS;
}

/**
 * The rows to draw at time `now`. With no trail, everything reported again up to `now`; with a trail, only the items
 * reported again after `now` minus that many months (the day exactly that many months back is out), up to `now`.
 */
export function visibleTrail(timeline: readonly Dated[], now: number, trailMonths: number | null): PointRow[] {
  const upto = countAt(timeline, now);
  if (trailMonths === null) return timeline.slice(0, upto).map((d) => d.row);
  const from = monthsBefore(now, trailMonths);
  return timeline.slice(0, upto).filter((d) => d.t > from).map((d) => d.row);
}

/** Seconds the whole animation takes at a speed (faster speed, shorter run). */
export function durationFor(baseSeconds: number, speed: number): number {
  return baseSeconds / (speed > 0 ? speed : 1);
}

/** The years that appear in a timeline, ascending, for the year range menus. */
export function yearsIn(timeline: readonly Dated[]): number[] {
  return [...new Set(timeline.map((d) => new Date(d.t).getUTCFullYear()))].sort((a, b) => a - b);
}
