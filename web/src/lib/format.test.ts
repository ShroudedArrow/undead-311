import fc from "fast-check";
import { describe, expect, it } from "vitest";
import { formatDateTime, formatDay, formatGap, roundDays } from "./format";

describe("format (REQ-WEB-CARD.1)", () => {
  it("shows Boston time, across the daylight-saving change", () => {
    expect(formatDateTime("2026-01-15T17:05:00Z")).toBe("Jan 15, 2026, 12:05 PM");
    expect(formatDateTime("2026-07-15T17:05:00Z")).toBe("Jul 15, 2026, 1:05 PM");
  });
  it("shows a bare date as written", () => {
    expect(formatDay("2026-03-01")).toBe("Mar 1, 2026");
  });
  it("returns empty for missing values and the input for junk", () => {
    expect(formatDateTime(null)).toBe("");
    expect(formatDay("not a date")).toBe("not a date");
  });
  it("rounds days to one decimal, never below zero for non-negative input", () => {
    fc.assert(fc.property(fc.double({ min: 0, max: 400, noNaN: true }), (d) => {
      const r = roundDays(d);
      expect(r).toBeGreaterThanOrEqual(0);
      expect(Math.abs(r - d)).toBeLessThanOrEqual(0.05 + 1e-9);
    }));
  });
});

describe("formatGap (REQ-WEB-CARD.1, UX-9)", () => {
  it("shows days from one day up, and hours or minutes below a day", () => {
    expect(formatGap(8.04)).toBe("8 days");
    expect(formatGap(1)).toBe("1 day");
    expect(formatGap(1.26)).toBe("1.3 days");
    expect(formatGap(5 / 24)).toBe("5 hours");
    expect(formatGap(1 / 24)).toBe("1 hour");
    expect(formatGap(10 / 1440)).toBe("10 minutes");
    expect(formatGap(1 / 1440)).toBe("1 minute");
    expect(formatGap(0.00001)).toBe("Less than a minute");
  });
  it("never says 0 days, for any non-negative gap", () => {
    fc.assert(fc.property(fc.double({ min: 0, max: 400, noNaN: true }), (d) => {
      const text = formatGap(d);
      expect(text).not.toMatch(/^0(\.0)? days?$/);
      expect(text.length).toBeGreaterThan(0);
    }));
  });
});
