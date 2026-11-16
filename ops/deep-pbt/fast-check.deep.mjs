// REQ-OPS-PBT.1: fast-check with every run count multiplied by 10, for the nightly deep job only.
// `vitest.deep.config.ts` aliases "fast-check" to this file, so the web tests' `import fc from "fast-check"` gets it.
// A global default (`configureGlobal`) would not reach a property that passes its own `{ numRuns }` (parse.test.ts: 60
// and 40); wrapping `assert` and `check` scales both the default and the pinned counts. The import is by path because
// this folder has no node_modules.
import * as real from "../../web/node_modules/fast-check/lib/fast-check.js";

export * from "../../web/node_modules/fast-check/lib/fast-check.js";

export const FACTOR = 10;
export const DEFAULT_RUNS = 100; // fast-check's own default

/** `params` with numRuns multiplied by FACTOR (the default of 100 when the test sets none). */
export function scale(params) {
  const given = params && typeof params.numRuns === "number" ? params.numRuns : DEFAULT_RUNS;
  return { ...(params ?? {}), numRuns: given * FACTOR };
}

export const assert = (property, params) => real.assert(property, scale(params));
export const check = (property, params) => real.check(property, scale(params));

export default { ...real, assert, check };
