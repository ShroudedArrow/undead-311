// REQ-OPS-PBT.1: the web's vitest config plus a setup file that raises fast-check's default runs 10x.
// Used only by .github/workflows/deep-pbt.yml: `cd web && npx vitest run --config ../ops/deep-pbt/vitest.deep.config.ts`.
// Imports are by path because this folder has no node_modules.
import { mergeConfig } from "../../web/node_modules/vitest/dist/config.js";
import base from "../../web/vite.config.ts";

export default mergeConfig(base, {
  test: { setupFiles: ["../ops/deep-pbt/fast-check-deep.setup.ts"] },
});
