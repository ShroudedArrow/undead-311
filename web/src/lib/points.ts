import type { FilterableZombie } from "./filter";
import { canonicalDepartment } from "./labels";
import type { PointsFile } from "./parse";

/** One map point: the filterable fields plus where to draw it. */
export interface PointRow extends FilterableZombie {
  lat: number;
  lon: number;
}

/** Turn the columnar points file into rows. Rows are in file order (the engine sorts by id). */
export function pointsToRows(p: PointsFile): PointRow[] {
  const rows: PointRow[] = [];
  const n = Math.min(p.n, p.id.length, p.lat.length, p.lon.length, p.tier.length, p.family.length, p.department.length, p.neighborhood.length, p.year.length);
  for (let i = 0; i < n; i++) {
    rows.push({
      id: p.id[i],
      lat: p.lat[i],
      lon: p.lon[i],
      tier: p.tier[i],
      family: p.family[i],
      department: canonicalDepartment(p.department[i]),
      neighborhood: p.neighborhood[i],
      year: p.year[i],
    });
  }
  return rows;
}
