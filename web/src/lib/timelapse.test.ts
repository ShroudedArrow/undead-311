import fc from "fast-check";
import { describe, expect, it } from "vitest";
import type { PointRow } from "./points";
import { buildTimeline, countAt, DAY_MS, durationFor, focusTimeline, monthsBefore, NO_FOCUS, SPEEDS, timeAt, TRAIL_MONTHS, visibleAt, visibleTrail, yearCounts, yearsIn } from "./timelapse";

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

describe("time-lapse focus, trail and speed (REQ-WEB-TIMELAPSE.1)", () => {
  const r = (id: string, family: string, neighborhood: string | null): PointRow => ({ ...row(id), family, neighborhood });
  const dates = new Map([["a", "2019-06-15"], ["b", "2020-01-31"], ["c", "2020-07-04"], ["d", "2021-03-01"]]);
  const rows = [r("a", "sign", "Dorchester"), r("b", "sidewalk", "Mattapan"), r("c", "sign", "Mattapan"), r("d", "sign", null)];
  const tl = buildTimeline(rows, dates);

  it("keeps everything with no focus, and narrows by family, neighborhood and year range", () => {
    expect(focusTimeline(tl, NO_FOCUS)).toEqual(tl);
    expect(focusTimeline(tl, { ...NO_FOCUS, family: "sign" }).map((d) => d.row.id)).toEqual(["a", "c", "d"]);
    expect(focusTimeline(tl, { ...NO_FOCUS, neighborhood: "Mattapan" }).map((d) => d.row.id)).toEqual(["b", "c"]);
    expect(focusTimeline(tl, { ...NO_FOCUS, fromYear: 2020, toYear: 2020 }).map((d) => d.row.id)).toEqual(["b", "c"]);
    expect(focusTimeline(tl, { family: "sign", neighborhood: "Mattapan", fromYear: 2020, toYear: 2021 }).map((d) => d.row.id)).toEqual(["c"]);
    expect(focusTimeline(tl, { ...NO_FOCUS, fromYear: 2022, toYear: null })).toEqual([]);
  });
  it("lists the years present, ascending", () => {
    expect(yearsIn(tl)).toEqual([2019, 2020, 2021]);
  });
  it("counts calendar months back, clamping the day", () => {
    expect(new Date(monthsBefore(Date.UTC(2020, 6, 4), 3)).toISOString().slice(0, 10)).toBe("2020-04-04");
    expect(new Date(monthsBefore(Date.UTC(2020, 4, 31), 3)).toISOString().slice(0, 10)).toBe("2020-02-29");
    expect(new Date(monthsBefore(Date.UTC(2020, 1, 15), 6)).toISOString().slice(0, 10)).toBe("2019-08-15");
  });
  it("shows everything so far with no trail, and only the last N months with one", () => {
    const now = Date.UTC(2020, 6, 4);
    expect(visibleTrail(tl, now, null).map((x) => x.id)).toEqual(["a", "b", "c"]);
    expect(visibleTrail(tl, now, 6).map((x) => x.id)).toEqual(["b", "c"]); // 2020-01-04 is the cut: Jan 31 stays, Jun 2019 goes
    expect(visibleTrail(tl, now, 3).map((x) => x.id)).toEqual(["c"]);
    expect(visibleTrail(tl, Date.UTC(2018, 0, 1), 3)).toEqual([]);
  });
  it("property: a trail never shows more than no trail, never shows a future item, and a longer trail never shows less", () => {
    fc.assert(fc.property(arb, fc.integer({ min: 16000, max: 20500 }), fc.constantFrom(...TRAIL_MONTHS), fc.constantFrom(...TRAIL_MONTHS), (xs, day, m1, m2) => {
      const t2 = make(xs);
      const now = day * DAY_MS;
      const all = new Set(visibleTrail(t2, now, null).map((x) => x.id));
      const [short, long] = m1 <= m2 ? [m1, m2] : [m2, m1];
      const a = new Set(visibleTrail(t2, now, short).map((x) => x.id));
      const b = new Set(visibleTrail(t2, now, long).map((x) => x.id));
      return [...a].every((id) => b.has(id)) && [...b].every((id) => all.has(id));
    }));
  });
  it("runs faster at a higher speed, and offers 1x", () => {
    expect(SPEEDS).toContain(1);
    expect(durationFor(24, 2)).toBe(12);
    expect(durationFor(24, 0.5)).toBe(48);
    expect(durationFor(24, 0)).toBe(24);
  });
});
