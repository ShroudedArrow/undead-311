import fc from "fast-check";
import { describe, expect, it } from "vitest";
import type { PointRow } from "./points";
import { buildTimeline, countAt, DAY_MS, timeAt, visibleAt, yearCounts } from "./timelapse";

const row = (id: string, tier: PointRow["tier"] = "headline"): PointRow => ({ id, lat: 42.3, lon: -71, tier, family: "sign", department: null, neighborhood: null, year: 2020 });
const arb = fc.array(fc.record({ id: fc.string({ minLength: 1, maxLength: 5 }), day: fc.integer({ min: 16000, max: 20500 }) }), { maxLength: 40 });
const make = (xs: { id: string; day: number }[]) => {
  const dates = new Map(xs.map((x) => [x.id, new Date(x.day * DAY_MS).toISOString().slice(0, 10)]));
  return buildTimeline([...dates.keys()].map((id) => row(id)), dates);
};

describe("time-lapse timeline (REQ-WEB-TIMELAPSE.1)", () => {
  it("keeps headline points with a valid date, sorted by date then ID", () => {
    const dates = new Map([["b", "2020-03-02"], ["a", "2020-03-02"], ["c", "2019-01-01"], ["x", "not a date"], ["s", "2018-01-01"]]);
    const tl = buildTimeline([row("b"), row("a"), row("c"), row("x"), row("s", "source_unknown"), row("none")], dates);
    expect(tl.map((d) => d.row.id)).toEqual(["c", "a", "b"]);
  });
  it("counts the items on or before a time", () => {
    const tl = make([{ id: "a", day: 17000 }, { id: "b", day: 17010 }, { id: "c", day: 17010 }]);
    expect(countAt(tl, 17000 * DAY_MS - 1)).toBe(0);
    expect(countAt(tl, 17000 * DAY_MS)).toBe(1);
    expect(countAt(tl, 17010 * DAY_MS)).toBe(3);
  });
  it("property: what is visible only grows as time moves on; before the start nothing, after the end everything", () => {
    fc.assert(fc.property(arb, fc.double({ min: 0, max: 1, noNaN: true }), fc.double({ min: 0, max: 1, noNaN: true }), (xs, a, b) => {
      const tl = make(xs);
      if (tl.length === 0) return true;
      const start = tl[0].t, end = tl[tl.length - 1].t;
      const [p, q] = a <= b ? [a, b] : [b, a];
      const early = new Set(visibleAt(tl, timeAt(start, end, p)).map((r) => r.id));
      const late = new Set(visibleAt(tl, timeAt(start, end, q)).map((r) => r.id));
      return [...early].every((id) => late.has(id)) && visibleAt(tl, start - 1).length === 0 && visibleAt(tl, end).length === tl.length;
    }));
  });
  it("progress is clamped to the span", () => {
    expect(timeAt(100, 200, -1)).toBe(100);
    expect(timeAt(100, 200, 2)).toBe(200);
    expect(timeAt(100, 200, NaN)).toBe(100);
  });
  it("property: the yearly table sums to the number of dated points and its running total ends there", () => {
    fc.assert(fc.property(arb, (xs) => {
      const tl = make(xs);
      const y = yearCounts(tl);
      return y.reduce((n, r) => n + r.count, 0) === tl.length && (y.length === 0 || y[y.length - 1].total === tl.length);
    }));
  });
});
