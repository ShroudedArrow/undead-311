import { describe, expect, it } from "vitest";
import { dataAsOfLabel, formatDate } from "./dataAsOf";

describe("Data as of label (REQ-WEB-FRESH.1)", () => {
  it("formats dates in UTC", () => {
    expect(formatDate("2026-11-13T23:30:00Z")).toBe("Nov 13, 2026");
  });
  it("prefers data_end over last_run", () => {
    expect(dataAsOfLabel({ data_end: "2026-11-10", last_run: "2026-11-13T02:00:00Z", ok: true })).toBe(
      "Data as of Nov 10, 2026",
    );
  });
  it("keeps the last good date and says the refresh failed (REQ-WEB-FRESH.2)", () => {
    expect(dataAsOfLabel({ last_run: "2026-11-12T02:00:00Z", ok: false })).toContain("last good data");
  });
  it("says so when there is no status", () => {
    expect(dataAsOfLabel(null)).toBe("Data date unavailable");
  });
});
