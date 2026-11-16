/**
 * Sensitivity sliders (REQ-WEB-SLIDERS.1): pure lookups into the precomputed grid of `sensitivity_grid.json`.
 * Nothing is recomputed in the browser; a setting that is not a grid point returns null and the page says so.
 */
import type { SensitivityGridFile } from "./parse";

export type GridPoint = SensitivityGridFile["points"][number];
export type Matching = GridPoint["matching"];
export interface Setting {
  matching: Matching;
  radius_m: number;
  window_days: number;
}

export const RADII = [15, 30, 50] as const;
export const WINDOWS = [30, 60, 90] as const;
export const MATCHINGS: readonly Matching[] = ["segment", "radius"];

/** The grid point for a setting, or null when the grid has none (REQ-WEB-SLIDERS.1). */
export function findPoint(grid: SensitivityGridFile, s: Setting): GridPoint | null {
  return grid.points.find((p) => p.matching === s.matching && p.radius_m === s.radius_m && p.window_days === s.window_days) ?? null;
}

/** True when the radius changes nothing for this matching: segment matching uses the radius only for unsnapped cases (zombie-definition Parameters). */
export const radiusIsMinor = (m: Matching): boolean => m === "segment";

/** The setting the run used, read from the file's `params` (REQ-STAT-GRID); the documented defaults when absent. */
export function defaultSetting(params?: { RADIUS_M?: number; WINDOW_DAYS?: number; matching?: string } | null): Setting {
  const radius = RADII.find((r) => r === params?.RADIUS_M) ?? 30;
  const window = WINDOWS.find((w) => w === params?.WINDOW_DAYS) ?? 60;
  return { matching: params?.matching === "radius" ? "radius" : "segment", radius_m: radius, window_days: window };
}

/** Index of a value in its slider's steps (a range input holds the step number, not the value). */
export const stepOf = (steps: readonly number[], v: number): number => Math.max(0, steps.indexOf(v));
