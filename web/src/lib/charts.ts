/**
 * Pure helpers for the survival and funnel charts and the leaderboards (REQ-WEB-CHARTS.1-2). No React here, so the rules
 * ("unusual" only outside the 99.8% limits; raw rankings never alone) are tested directly.
 */
import type { Curve, FunnelLimit, Group } from "./parse";

export type CurveKind = "all" | "family" | "department";
export const FAMILY_KEYS = ["pothole_roadway", "streetlight", "sidewalk", "sign", "traffic_signal", "pavement_marking", "street_fixture"];

/** The engine names curves "all", "family:<key>" or "department:<code>". A bare family key is also accepted. */
export function curveKind(name: string): { kind: CurveKind; key: string } {
  if (name === "all") return { kind: "all", key: "all" };
  const m = /^(family|department):(.*)$/.exec(name);
  if (m) return { kind: m[1] as CurveKind, key: m[2] };
  return { kind: FAMILY_KEYS.includes(name) ? "family" : "department", key: name };
}

export function curvesFor(curves: readonly Curve[], tierSet: "headline" | "all", kind: CurveKind): Curve[] {
  return curves.filter((c) => c.tier_set === tierSet && curveKind(c.name).kind === kind);
}

/** True when the curve starts at 1 and never rises (testing.md #6). */
export function isValidCurve(c: Pick<Curve, "survival">): boolean {
  const s = c.survival;
  return s.length > 0 && s[0] === 1 && s.every((v, i) => i === 0 || v <= s[i - 1]);
}

export interface Scale {
  (v: number): number;
}
export function linear(d0: number, d1: number, r0: number, r1: number): Scale {
  const span = d1 - d0 || 1;
  return (v) => r0 + ((v - d0) / span) * (r1 - r0);
}
export function logScale(d0: number, d1: number, r0: number, r1: number): Scale {
  const a = Math.log(Math.max(d0, 1e-9));
  const b = Math.log(Math.max(d1, 1e-9));
  return (v) => r0 + ((Math.log(Math.max(v, 1e-9)) - a) / (b - a || 1)) * (r1 - r0);
}

/** SVG path for a line through points. */
export function linePath(xs: readonly number[], ys: readonly number[]): string {
  return xs.map((x, i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)} ${ys[i].toFixed(1)}`).join(" ");
}

/** SVG path for the band between a lower and an upper line. */
export function bandPath(xs: readonly number[], lo: readonly number[], hi: readonly number[]): string {
  const top = xs.map((x, i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)} ${hi[i].toFixed(1)}`);
  const back = xs.map((x, i) => `L${x.toFixed(1)} ${lo[i].toFixed(1)}`).reverse();
  return `${top.join(" ")} ${back.join(" ")} Z`;
}

/**
 * The control limits that apply to a group of size n: the entry with the largest n' <= n. Limits narrow as n grows,
 * so the floor entry is the wider (more cautious) one when the file lists only some n values.
 */
export function limitAt(limits: readonly FunnelLimit[], n: number): FunnelLimit | null {
  let best: FunnelLimit | null = null;
  for (const l of limits) if (l.n <= n && (best === null || l.n > best.n)) best = l;
  return best ?? (limits.length ? limits.reduce((a, b) => (a.n <= b.n ? a : b)) : null);
}

/**
 * REQ-WEB-CHARTS.2: a group is called "unusual" only when the file says so AND its raw rate lies outside the 99.8%
 * limits for its n. A group inside the limits is never unusual, whatever the file says.
 */
export function isUnusual(g: Pick<Group, "n" | "raw" | "unusual">, limits: readonly FunnelLimit[]): boolean {
  if (!g.unusual || g.raw === null) return false;
  const l = limitAt(limits, g.n);
  return l !== null && (g.raw < l.lo998 || g.raw > l.hi998);
}

export interface LeaderRow extends Group {
  /** Whether the "unusual" tag may be shown (see isUnusual). */
  unusualShown: boolean;
}

/**
 * Leaderboard rows for one kind, ordered by the shrunk rate, highest first (ties by name). The raw rate is a column
 * beside it, never the sort key, so a raw ranking never appears alone (REQ-WEB-CHARTS.2).
 */
export function leaderboard(groups: readonly Group[], kind: Group["kind"], limits: readonly FunnelLimit[]): LeaderRow[] {
  return groups
    .filter((g) => g.kind === kind)
    .map((g) => ({ ...g, unusualShown: isUnusual(g, limits) }))
    .sort((a, b) => (b.shrunk ?? -1) - (a.shrunk ?? -1) || (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
}

/** "12 per km" style value, or null when the file has no reporting intensity. */
export function intensityText(g: Pick<Group, "reports_per_km">): string | null {
  return g.reports_per_km === null || g.reports_per_km === undefined ? null : g.reports_per_km.toFixed(1);
}
