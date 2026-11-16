import fc from "fast-check";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { parseSensitivityGrid } from "./parse";
import { defaultSetting, findPoint, MATCHINGS, RADII, stepOf, WINDOWS } from "./sensitivity";

const raw = JSON.parse(readFileSync(join(__dirname, "..", "..", "public", "data", "stats", "sensitivity_grid.json"), "utf8"));
const parsed = parseSensitivityGrid(raw);
if (!parsed.ok) throw new Error("grid does not parse");
const grid = parsed.data;

describe("sensitivity grid lookups (REQ-WEB-SLIDERS.1)", () => {
  it("finds exactly one point for every combination of matching, radius and window", () => {
    for (const matching of MATCHINGS) for (const radius_m of RADII) for (const window_days of WINDOWS) {
      const hits = grid.points.filter((p) => p.matching === matching && p.radius_m === radius_m && p.window_days === window_days);
      expect(hits, `${matching} ${radius_m} ${window_days}`).toHaveLength(1);
      expect(findPoint(grid, { matching, radius_m, window_days })).toBe(hits[0]);
    }
  });
  it("returns null for a setting the grid does not hold", () => {
    expect(findPoint(grid, { matching: "segment", radius_m: 20, window_days: 60 })).toBeNull();
    expect(findPoint({ ...grid, points: [] }, { matching: "segment", radius_m: 30, window_days: 60 })).toBeNull();
  });
  it("the default setting is the run the headline came from", () => {
    const d = defaultSetting((raw as { params: Record<string, unknown> }).params);
    expect(findPoint(grid, d)?.headline).toBe(1009);
  });
  it("property: lookups are deterministic and slider steps round-trip", () => {
    fc.assert(
      fc.property(fc.constantFrom(...MATCHINGS), fc.constantFrom(...RADII), fc.constantFrom(...WINDOWS), (matching, radius_m, window_days) => {
        const a = findPoint(grid, { matching, radius_m, window_days });
        const b = findPoint(grid, { matching, radius_m, window_days });
        return a === b && a !== null && RADII[stepOf(RADII, radius_m)] === radius_m && WINDOWS[stepOf(WINDOWS, window_days)] === window_days;
      }),
    );
  });
  it("property: a longer window never reports fewer headline zombies at one matching and distance", () => {
    fc.assert(
      fc.property(fc.constantFrom(...MATCHINGS), fc.constantFrom(...RADII), (matching, radius_m) => {
        const h = WINDOWS.map((window_days) => findPoint(grid, { matching, radius_m, window_days })?.headline ?? -1);
        return h.every((v, i) => i === 0 || v >= h[i - 1] - 0);
      }),
    );
  });
});
