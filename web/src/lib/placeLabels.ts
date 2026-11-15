/**
 * Neighborhood name labels for the home map (ops#18, owner decision 6). Pure: one label per neighborhood, placed at the
 * median position of its points, so a few far-off points do not drag the name away from where most of them are.
 */
import type { PointRow } from "./points";

export interface PlaceLabel {
  name: string;
  lat: number;
  lon: number;
  count: number;
}

const median = (xs: number[]): number => {
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};

/** Labels for neighborhoods with at least `minPoints` points, sorted by name. Rows with no neighborhood are ignored. */
export function neighborhoodLabels(rows: readonly PointRow[], minPoints = 3): PlaceLabel[] {
  const by = new Map<string, PointRow[]>();
  for (const r of rows) if (r.neighborhood) by.set(r.neighborhood, [...(by.get(r.neighborhood) ?? []), r]);
  return [...by.entries()]
    .filter(([, rs]) => rs.length >= minPoints)
    .map(([name, rs]) => ({ name, lat: median(rs.map((r) => r.lat)), lon: median(rs.map((r) => r.lon)), count: rs.length }))
    .sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
}
