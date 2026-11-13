import fc from "fast-check";
import { describe, expect, it } from "vitest";
import { DEFAULT_STATE, decodeState, encodeState, type PageState } from "./url";

const arbState: fc.Arbitrary<PageState> = fc.record({
  filters: fc.record({
    neighborhoods: fc.uniqueArray(fc.string({ minLength: 1, maxLength: 8 }), { maxLength: 4 }).map((a) => a.sort()),
    departments: fc.uniqueArray(fc.string({ minLength: 1, maxLength: 8 }), { maxLength: 3 }).map((a) => a.sort()),
    families: fc.uniqueArray(fc.constantFrom("sign", "sidewalk", "streetlight"), { maxLength: 3 }).map((a) => a.sort()),
    years: fc.uniqueArray(fc.integer({ min: 2015, max: 2026 }), { maxLength: 5 }).map((a) => a.sort((x, y) => x - y)),
  }),
  tierMode: fc.constantFrom("headline", "all"),
  view: fc.constantFrom("map", "table"),
});

describe("URL state (REQ-WEB-MAP.3)", () => {
  it("round-trips any state", () => {
    fc.assert(
      fc.property(arbState, (s) => {
        expect(decodeState(encodeState(s))).toEqual(s);
      }),
    );
  });
  it("the default state encodes to an empty query", () => {
    expect(encodeState(DEFAULT_STATE)).toBe("");
    expect(decodeState("")).toEqual(DEFAULT_STATE);
  });
  it("ignores junk values", () => {
    expect(decodeState("y=abc&tier=zzz&view=x").filters.years).toEqual([]);
    expect(decodeState("tier=zzz").tierMode).toBe("headline");
  });
});
