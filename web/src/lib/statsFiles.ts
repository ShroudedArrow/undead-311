/**
 * REQ-WEB-DATA.1 (owner decision, issue 101 in the ops repo): the statistics files sit under `data/stats/`; every other data file sits
 * flat under `data/`. Plain TypeScript with no Vite imports, so the build scripts can use it too.
 */
export const STATS_FILES: readonly string[] = [
  "scorecard.json",
  "judge_tour.json",
  "excess.json",
  "survival.json",
  "funnel.json",
  "groups.json",
  "sensitivity_grid.json",
  "temporary_fixes.json",
  "validation.json",
];

/** The path of a data file relative to `data/`: `stats/<name>` for a statistics file, the name itself otherwise. */
export function statsPath(file: string): string {
  return STATS_FILES.includes(file) ? `stats/${file}` : file;
}
