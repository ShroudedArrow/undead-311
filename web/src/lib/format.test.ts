import fc from "fast-check";
import { describe, expect, it } from "vitest";
import { formatDateTime, formatDay, roundDays } from "./format";

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
