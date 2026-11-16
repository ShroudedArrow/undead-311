import { readFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
// @ts-expect-error plain .mjs script, no type declarations
import { generate } from "../../../scripts/gen-parsers.mjs";

describe("generated parsers are up to date (REQ-WEB-DATA.1)", () => {
  it("matches what scripts/gen-parsers.mjs writes from /schemas", async () => {
    const files = (await generate()) as Record<string, string>;
    for (const [name, text] of Object.entries(files)) {
      const p = join(__dirname, "generated", name);
      expect(existsSync(p), `${name} missing: run node scripts/gen-parsers.mjs`).toBe(true);
      expect(readFileSync(p, "utf8") === text, `${name} is stale: run node scripts/gen-parsers.mjs`).toBe(true);
    }
  });
});
