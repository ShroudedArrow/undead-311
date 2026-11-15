import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { NULL_TOWNS, STRESS_ABOVE, STRESS_TOWNS, signed, sumOf } from "./nullTowns";

const doc = readFileSync(join(__dirname, "..", "..", "..", "docs", "METHODS.md"), "utf8");

interface DocRow { label: string; seed: number; excess: number; where: string }
/** Table rows of docs/METHODS.md between the first `| Null town |` header after `from` and the `Counts:` line that follows. */
function tableRows(from: string, until: string): DocRow[] {
  const start = doc.indexOf(from);
  const end = doc.indexOf(until, start);
  if (start < 0 || end < 0) throw new Error(`docs/METHODS.md no longer has ${from} or ${until}`);
  return doc.slice(start, end).split("\n").filter((l) => l.startsWith("| ") && !l.startsWith("| Null town") && !l.startsWith("|---")).map((l) => {
    const c = l.split("|").map((x) => x.trim());
    return { label: c[1].replace(/ \(ops#\d+\)$/, ""), seed: Number(c[2]), excess: Number(c[6].split(" ")[0].replace(/[+,]/g, "")), where: c[7] };
  });
}

describe("null-town figures on the methods page match docs/METHODS.md (REQ-WEB-METHODS.1; ops#130)", () => {
  const rows = tableRows("| Null town | Seed |", "Counts: 40 towns");

  it("has 40 towns, none with the interval above 0, and the page totals agree", () => {
    expect(rows).toHaveLength(40);
    expect(rows.some((r) => r.where.startsWith("above"))).toBe(false);
    expect(sumOf("above")).toBe(0);
    expect(sumOf("below") + sumOf("covers")).toBe(40);
    expect(rows.filter((r) => r.where === "below 0")).toHaveLength(sumOf("below"));
    expect(rows.filter((r) => r.where === "covers 0")).toHaveLength(sumOf("covers"));
    expect(doc).toContain("Counts: 40 towns, none with an interval above 0; 32 lie below 0 (cautious) and 8 cover 0");
  });

  it.each(NULL_TOWNS.map((r) => [r.id, r] as const))("row %s equals what the document's table says", (_id, r) => {
    const mine = rows.filter((d) => d.label === r.doc);
    expect(mine.length).toBeGreaterThan(0);
    const seeds = mine.map((d) => d.seed);
    expect(r.seeds).toBe(`${Math.min(...seeds)}-${Math.max(...seeds)}`);
    expect(r.min).toBe(Math.min(...mine.map((d) => d.excess)));
    expect(r.max).toBe(Math.max(...mine.map((d) => d.excess)));
    expect(r.below).toBe(mine.filter((d) => d.where === "below 0").length);
    expect(r.covers).toBe(mine.filter((d) => d.where === "covers 0").length);
    expect(r.above).toBe(mine.filter((d) => d.where.startsWith("above")).length);
  });

  it("covers every town of the document's first table", () => {
    expect(new Set(NULL_TOWNS.map((r) => r.doc))).toEqual(new Set(rows.map((d) => d.label)));
  });

  it("the stress-town counts match the document's second table", () => {
    const stress = tableRows("Near-regular, staggered and limit towns", "Counts: 48 towns");
    expect(stress).toHaveLength(STRESS_TOWNS);
    expect(stress.filter((r) => r.where.startsWith("above"))).toHaveLength(STRESS_ABOVE);
  });

  it("signed keeps an ASCII sign", () => {
    expect([signed(5), signed(0), signed(-5)]).toEqual(["+5", "0", "-5"]);
  });
});
