// REQ-OPS-PBT.1: raise fast-check's default number of runs 10x for the nightly deep job.
// Loaded only by .github/workflows/deep-pbt.yml (`vitest run --setupFiles ../ops/deep-pbt/fast-check-deep.setup.ts`);
// the normal `npm test` never sees it. The import is by path because this folder has no node_modules; it resolves to
// the same module file the tests import as "fast-check", so the global setting applies to them.
import fc from "../../web/node_modules/fast-check/lib/fast-check.js";

const FACTOR = 10;
const DEFAULT_RUNS = 100; // fast-check's own default
fc.configureGlobal({ numRuns: DEFAULT_RUNS * FACTOR });
