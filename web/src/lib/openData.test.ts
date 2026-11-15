import fc from "fast-check";
import { describe, expect, it } from "vitest";
import type { Zombie } from "./parse";
import { districtSummaries, OPEN_COLUMNS, parseCsv, zombiesToCsv } from "./openData";

const z = (over: Record<string, unknown> = {}): Zombie => ({ zombie_id: "a:b", tier: "headline", type_family: "sign", district: "3", resurrection_date: "2020-05-01", gap_days: 3, ...over }) as unknown as Zombie;

describe("open data CSV (REQ-WEB-OPEN.1)", () => {
  it("writes the header and one row per zombie, quoting commas, quotes and line breaks", () => {
    const csv = zombiesToCsv([z({ zombie_id: 'x,"y"', skeptic_notes: "a\nb", neighborhood: "Allston / Brighton" })]);
    const rows = parseCsv(csv);
    expect(rows[0]).toEqual([...OPEN_COLUMNS]);
    expect(rows[1][0]).toBe('x,"y"');
    expect(rows).toHaveLength(2);
    expect(csv.endsWith("\r\n")).toBe(true);
  });
  it("property: any zombie ids and neighborhoods read back unchanged, one row each", () => {
    fc.assert(
      fc.property(fc.array(fc.record({ id: fc.string({ maxLength: 12 }), hood: fc.option(fc.string({ maxLength: 12 }), { nil: null }) }), { maxLength: 12 }), (xs) => {
        const rows = parseCsv(zombiesToCsv(xs.map((x) => z({ zombie_id: x.id, neighborhood: x.hood }))));
        const iId = OPEN_COLUMNS.indexOf("zombie_id");
        const iHood = OPEN_COLUMNS.indexOf("neighborhood");
        // a lone empty-string ID makes a blank-looking row in some readers; the reader here keeps it
        return rows.length === xs.length + 1 && xs.every((x, i) => rows[i + 1][iId] === x.id && rows[i + 1][iHood] === (x.hood ?? ""));
      }),
    );
  });
});

describe("district summaries (REQ-WEB-OPEN.2)", () => {
  it("counts headline zombies per district and leaves out zombies with no district and other tiers", () => {
    const out = districtSummaries([z(), z({ type_family: "sidewalk" }), z({ district: "10" }), z({ district: null }), z({ tier: "city_rereport" }), z({ district: "2", resurrection_date: "2019-01-01" })]);
    expect(out.map((d) => [d.district, d.count])).toEqual([["2", 1], ["3", 2], ["10", 1]]);
    expect(out[1].byFamily).toEqual([{ family: "sidewalk", count: 1 }, { family: "sign", count: 1 }]);
    expect(out[0].byYear).toEqual([{ year: 2019, count: 1 }]);
  });
  it("property: district counts add up to the headline zombies that have a district", () => {
    fc.assert(
      fc.property(fc.array(fc.record({ tier: fc.constantFrom("headline", "city_rereport"), district: fc.option(fc.constantFrom("1", "2", "9"), { nil: null }) }), { maxLength: 30 }), (xs) => {
        const out = districtSummaries(xs.map((x) => z(x)));
        const expected = xs.filter((x) => x.tier === "headline" && x.district).length;
        return out.reduce((n, d) => n + d.count, 0) === expected && out.every((d) => d.byFamily.reduce((n, f) => n + f.count, 0) === d.count);
      }),
    );
  });
});
