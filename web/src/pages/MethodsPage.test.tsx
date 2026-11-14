import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { clearDataCache } from "../lib/data";

const V = "v";
const rate = (rate: number | null, k: number, n: number) => (n === 0 ? { rate: null, lo: null, hi: null, k, n, reason: "no cases" } : { rate, lo: Math.max(0, (rate as number) - 0.05), hi: (rate as number) + 0.05, k, n });
const FILES: Record<string, unknown> = {
  "status.json": { data_version: V, last_run: "2026-11-11T02:00:00Z", ok: true, row_counts: { cases: 100, zombies: 7 }, anomalies: ["66% of headline resurrections are legacy city-originated cases"], segments: "missing", calibration_warning: null, source_unknown_count: 49, data_end: "2026-11-11" },
  "scorecard.json": { data_version: V, scorecards: [], counts: { headline: 1, source_unknown: 1, sensitivity: 0 }, params: { WINDOW_DAYS: 60, RADIUS_M: 30, matching: "segment" }, seed: null },
  "excess.json": {
    data_version: V,
    rows: [
      { kind: "family", name: "sign", observed: 20, expected: 5.25, excess: 14.75, lo: 10, hi: 19, tier_set: "headline" },
      { kind: "family", name: "sidewalk", observed: 40, expected: 8, excess: 32, lo: 25, hi: 39, tier_set: "headline" },
      { kind: "family", name: "sign", observed: 25, expected: 6, excess: 19, lo: 12, hi: 26, tier_set: "all" },
      { kind: "department", name: "PWDx", observed: 60, expected: 13, excess: 47, lo: 40, hi: 54, tier_set: "headline" },
    ],
    shift: { runs: 1000, seed: 311, observed: 60, mean: 13.3, q025: 8, q975: 19 },
    placebo: { excess: 0.4, lo: -3.1, hi: 3.9 },
  },
  "validation.json": { data_version: V, status: "awaiting_field_labels", precision: null, cant_tell_share: null, kappa: null, confirmed: [], sample_ids: [] },
  "temporary_fixes.json": {
    data_version: V,
    rows: [{ family: "pothole_roadway", department: null, n_made_safe: 100, after_temporary_fix: rate(0.17, 17, 100), source_unknown: rate(0.03, 3, 100) }, { family: "sign", department: null, n_made_safe: 0, after_temporary_fix: rate(null, 0, 0), source_unknown: rate(null, 0, 0) }],
    separate_deaths: { invalid: 5, duplicate: 11 },
    exclusions: {},
  },
  "exclusions.json": { data_version: V, counts: { excluded_type: 0, null_coords: 3 }, excluded_ids: {}, excluded_pairs: { mirror: 15, transferred_original: 49, linked_successor: 0 } },
  "bulk_closures.json": { data_version: V, bulk_closures: [{ department: "PWDx", close_date: "2020-03-05", template: "Case closed. Closed date", n_cases: 80, usual_daily: 4, ratio: 20 }] },
};

function stub(overrides: Record<string, unknown> = {}, failing: string[] = []) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const file = String(url).split("/").pop() as string;
    if (failing.includes(file)) return { ok: false, status: 500, json: async () => ({}) } as Response;
    return { ok: true, status: 200, json: async () => ({ ...FILES, ...overrides })[file] ?? {} } as Response;
  }));
}
afterEach(() => { vi.unstubAllGlobals(); clearDataCache(); });
const open = () => render(<MemoryRouter initialEntries={["/methods"]}><App /></MemoryRouter>);

describe("Methods page (REQ-WEB-METHODS.1)", () => {
  it("leaves the introduction as a TODO-COPY placeholder and shows the definitions with this data's parameters", async () => {
    stub();
    open();
    expect(screen.getByTestId("methods-intro").textContent).toMatch(/^TODO-COPY:/);
    expect(await screen.findByText(/within 60 days of the closure/)).toBeTruthy();
    expect(screen.getByText(/within 30 meters/)).toBeTruthy();
    expect(screen.getByText(/matching segment, radius 30 meters, window 60 days/)).toBeTruthy();
  });
  it("shows the excess by case type with intervals, the shift distribution and the placebo result", async () => {
    stub();
    open();
    const table = await screen.findByTestId("excess-table");
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.map((r) => r.querySelector("th")?.textContent)).toEqual(["Sidewalks", "Signs"]);
    expect(rows[1].textContent).toContain("5.3");
    expect(rows[1].textContent).toContain("10 to 19");
    expect(screen.getByTestId("shift-observed").textContent).toBe("Observed: 60 possible zombies");
    expect(screen.getByTestId("shift-range").textContent).toBe("By chance: mean 13.3; 95% of shifted runs fall between 8 and 19");
    expect(screen.getByTestId("placebo").textContent).toBe("Placebo excess 0.4, 95% interval -3.1 to 3.9");
  });
  it("says so when the shift and placebo results are missing, instead of inventing them", async () => {
    stub({ "excess.json": { ...(FILES["excess.json"] as object), shift: undefined, placebo: undefined } });  // a malformed result no longer reaches the page: the schema rejects it (ops#92)
    open();
    expect(await screen.findByText("The shift-test distribution is not part of this data yet.")).toBeTruthy();
    expect(screen.getByText("The placebo result is not part of this data yet.")).toBeTruthy();
    expect(screen.queryByTestId("placebo")).toBeNull();
  });
  it("shows validation as awaiting field labels, then precision with its interval and kappa once scored", async () => {
    stub();
    const { unmount } = open();
    expect(await screen.findByTestId("validation-awaiting")).toBeTruthy();
    unmount();
    clearDataCache();
    stub({ "validation.json": { data_version: V, status: "scored", precision: { rate: 0.8, lo: 0.7, hi: 0.88, k: 40, n: 50 }, cant_tell_share: 0.1, kappa: 0.72, confirmed: ["a"], sample_ids: [] } });
    open();
    const scored = await screen.findByTestId("validation-scored");
    expect(scored.textContent).toContain("Precision 80.0%, 95% interval 70.0% to 88.0%, from 50 rated possible zombies.");
    expect(scored.textContent).toContain("kappa): 0.72");
    expect(scored.textContent).toContain("Could not tell: 10.0% of the sample.");
  });
  it("states the limits: counts are a floor and the intersection note", async () => {
    stub();
    open();
    expect(await screen.findByText(/Counts are a floor/)).toBeTruthy();
    expect(screen.getByText(/An endpoint is a segment break, not always a cross street/)).toBeTruthy();
  });
  it("shows the nightly status with anomalies, and a failed run says the last good data stays", async () => {
    stub();
    const { unmount } = open();
    const box = await screen.findByTestId("nightly-status");
    expect(box.textContent).toContain("The latest run succeeded.");
    expect(box.textContent).toContain("66% of headline resurrections are legacy city-originated cases");
    expect(box.textContent).toContain("Rows read: cases 100");
    unmount();
    clearDataCache();
    stub({ "status.json": { ...(FILES["status.json"] as object), ok: false, calibration_warning: "placebo interval excludes 0" } });
    open();
    expect((await screen.findByTestId("nightly-status")).textContent).toContain("The site keeps showing the last good data.");
    expect(screen.getByTestId("calibration-warning").textContent).toBe("Calibration warning: placebo interval excludes 0");
  });
  it("offers Report an error and the corrections log", async () => {
    stub();
    open();
    const link = await screen.findByRole("link", { name: "Report an error" });
    expect(link.getAttribute("href")).toContain("/issues/new?title=Error%20report%3A%20Methods");
    expect(screen.getByRole("link", { name: "Corrections log" }).getAttribute("href")).toBe("/corrections");
  });
  it("one failed file shows an error for its panel only", async () => {
    stub({}, ["excess.json"]);
    open();
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(await screen.findByTestId("nightly-status")).toBeTruthy();
  });
});

describe("What the headline leaves out (REQ-WEB-DEATHS.1)", () => {
  it("shows separate deaths, temporary-fix return rates with intervals, exclusions and bulk-closure days", async () => {
    stub();
    open();
    expect((await screen.findByTestId("separate-deaths")).textContent).toContain("Invalid: 5. Duplicate: 11.");
    const temp = screen.getByTestId("temp-fixes");
    expect(temp.textContent).toContain("17.0% (12.0% to 22.0%), n = 100");
    expect(within(temp).getAllByText("No cases", { selector: "td" })).toHaveLength(2);
    const ex = screen.getByTestId("exclusions");
    expect(within(ex).getByText("Mirror copies across the two systems").closest("tr")?.textContent).toContain("15");
    expect(within(ex).getByText("No usable coordinates").closest("tr")?.textContent).toContain("3");
    expect(screen.getByTestId("bulk-table").textContent).toContain("2020-03-05");
    expect(screen.getByRole("link", { name: "Mark these possible zombies on the map" }).getAttribute("href")).toBe("/?bulk=1");
  });
  it("explains source unknown with its count and says it is never added to the headline", async () => {
    stub();
    open();
    const text = (await screen.findByTestId("source-unknown-text")).textContent as string;
    expect(text).toContain("The 49 possible zombies of this kind sit outside the headline count and are never added to it.");
    expect(within(screen.getByTestId("source-unknown-text")).getByRole("link").getAttribute("href")).toBe("/?tier=all");
  });
  it("says so when there are no bulk-closure days", async () => {
    stub({ "bulk_closures.json": { data_version: V, bulk_closures: [] } });
    open();
    expect(await screen.findByTestId("bulk-none")).toBeTruthy();
  });
  it("offers no map-layer link when there are no bulk-closure days (UX-18)", async () => {
    stub({ "bulk_closures.json": { data_version: V, bulk_closures: [] } });
    open();
    await screen.findByTestId("bulk-none");
    expect(screen.queryByRole("link", { name: "Mark these possible zombies on the map" })).toBeNull();
  });
  it("explains zero exclusion counts on preview data, and not on real data (UX-25)", async () => {
    stub({ "status.json": { data_version: "fixture-2026-11-11", last_run: "2026-11-11T00:00:00Z", ok: true, row_counts: {}, anomalies: [], segments: "missing" } });
    open();
    expect(await screen.findByTestId("excl-fixture-note")).toBeTruthy();
  });
});
