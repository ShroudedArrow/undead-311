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
