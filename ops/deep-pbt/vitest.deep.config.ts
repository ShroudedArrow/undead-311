// REQ-OPS-PBT.1: the web's vitest config with "fast-check" aliased to a copy whose run counts are 10x (fast-check.deep.mjs).
// Used only by .github/workflows/deep-pbt.yml: `cd web && npx vitest run --config ../ops/deep-pbt/vitest.deep.config.ts`.
// Imports are by path because this folder has no node_modules.
import { fileURLToPath } from "node:url";
import { mergeConfig } from "../../web/node_modules/vitest/dist/config.js";
import base from "../../web/vite.config.ts";

export default mergeConfig(base, {
  resolve: { alias: { "fast-check": fileURLToPath(new URL("./fast-check.deep.mjs", import.meta.url)) } },
});
