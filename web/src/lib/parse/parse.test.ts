import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import fc from "fast-check";
import { describe, expect, it } from "vitest";
import { arbFromSchema, type Schema } from "./schemaArb";
import { REGISTRY } from "./registry";
import { parseStatus, parseZombies } from "./index";

const schemaDir = join(__dirname, "..", "..", "..", "..", "schemas");
const stems = Object.keys(REGISTRY);

function loadSchema(stem: string): Schema {
  return JSON.parse(readFileSync(join(schemaDir, `${stem}.schema.json`), "utf8")) as Schema;
}

describe("Property W1: parsers match the schemas (REQ-WEB-DATA.1, testing.md #16)", () => {
  it("has a parser for every web-facing schema", () => {
    const onDisk = readdirSync(schemaDir)
      .filter((f) => f.endsWith(".schema.json"))
      .map((f) => f.replace(".schema.json", ""))
      .filter((s) => s !== "test_town_expected");
    expect(stems.sort()).toEqual(onDisk.sort());
  });

  for (const stem of stems) {
    const schema = loadSchema(stem);

    it(`${stem}: accepts every schema-valid generated file`, () => {
      fc.assert(
        fc.property(arbFromSchema(schema), (file) => {
          const r = REGISTRY[stem](file);
          expect(r, JSON.stringify(r)).toMatchObject({ ok: true });
        }),
        { numRuns: 60 },
      );
    });

    it(`${stem}: rejects a file that misses any required top-level field`, () => {
      const required = schema.required ?? [];
      fc.assert(
        fc.property(arbFromSchema(schema), fc.constantFrom(...required), (file, field) => {
          const broken = { ...(file as Record<string, unknown>) };
          delete broken[field];
          expect(REGISTRY[stem](broken).ok).toBe(false);
        }),
        { numRuns: 40 },
      );
    });

    it(`${stem}: rejects non-objects`, () => {
      for (const bad of [null, 7, "x", [], undefined]) expect(REGISTRY[stem](bad).ok).toBe(false);
    });
  }

  it("names the missing field in the error (REQ-WEB-DATA.2)", () => {
    const r = parseStatus({ data_version: "x" });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error).toMatch(/last_run|ok|anomalies|row_counts|segments/);
  });

  it("rejects a wrong tier value", () => {
    expect(parseZombies({ data_version: "x", zombies: [{ tier: "loud" }] }).ok).toBe(false);
  });
});
