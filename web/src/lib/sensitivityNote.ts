import type { SensitivityGridFile } from "./parse";
import { findPoint } from "./sensitivity";

/** Headline counts for the 90-day window and for the 60-day headline run at the same matching and distance (REQ-WEB-STREET.1, REQ-WEB-SLIDERS.1); null when the grid lacks either. */
export function methodsPageSettings(grid: SensitivityGridFile): { headline: number; base: number } | null {
  const p = (grid as { params?: { RADIUS_M?: number; matching?: string } }).params;
  const s = { matching: (p?.matching === "radius" ? "radius" : "segment") as "segment" | "radius", radius_m: p?.RADIUS_M ?? 30 };
  const wide = findPoint(grid, { ...s, window_days: 90 });
  const base = findPoint(grid, { ...s, window_days: 60 });
  return wide && base ? { headline: wide.headline, base: base.headline } : null;
}
