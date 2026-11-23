import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { clearDataCache } from "../lib/data";

const V = "v";
const rate = (rate: number | null, k: number, n: number) => (n === 0 ? { rate: null, lo: null, hi: null, k, n, reason: "no cases" } : { rate, lo: Math.max(0, (rate as number) - 0.05), hi: (rate as number) + 0.05, k, n });
const FILES: Record<string, unknown> = {
  "status.json": { data_version: V, last_run: "2026-11-11T02:00:00Z", ok: true, row_counts: { cases: 100, zombies: 7 }, anomalies: ["66% of headline resurrections are legacy city-originated cases"], segments: "missing", calibration_warning: null, source_unknown_count: 49, data_end: "2026-11-11" },
  "scorecard.json": { data_version: V, scorecards: [], counts: { headline: 1, source_unknown: 1, city_rereport: 0, sensitivity: 0 }, params: { WINDOW_DAYS: 60, RADIUS_M: 30, matching: "segment" }, seed: null },
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
  "sensitivity_grid.json": { data_version: V, params: { WINDOW_DAYS: 60, RADIUS_M: 30, matching: "segment" }, points: [{ matching: "segment", radius_m: 30, window_days: 60, headline: 1, source_unknown: 0, city_rereport: 0, sensitivity: 0, excess: 1.5, stayed_fixed_rate: 0.5 }], without_street_light_other: { headline: 1, all_tiers: 1 } },
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
  it("opens with the written introduction, shows the definitions with this data's parameters, and ends with the \"Who made this\" section", async () => {
    stub();
    open();
    expect((await screen.findByTestId("methods-intro")).textContent).toMatch(/^A possible zombie is a 311 case that was closed/);
    const about = screen.getByTestId("about");
    expect(within(about).getByRole("heading", { name: "Who made this" })).toBeTruthy();
    expect(about.textContent).toMatch(/Not affiliated with the City of Boston\.$/);
    expect(screen.getByTestId("about").closest(".methods-main")?.lastElementChild).toBe(about);
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
  it("says the adjusted rate is not shown and the confidence score is for ranking only (owner decision 2026-11-17)", async () => {
    stub();
    open();
    expect((await screen.findByTestId("adjusted-text")).textContent).toMatch(/same baseline as the excess.*not calibrated.*not shown anywhere/);
    expect(screen.getByTestId("confidence-text").textContent).toMatch(/cautious, uncalibrated baseline.*only to rank/);
  });
  it("withholds the excess and shows the placebo instead when the headline placebo does not cover 0 (methods.md, owner rule 2026-11-16)", async () => {
    stub({ "excess.json": { ...(FILES["excess.json"] as object), placebo: { excess: -3152, lo: -3368, hi: -2932 } } });
    open();
    expect((await screen.findByTestId("excess-withheld")).textContent).toContain("is not shown");
    expect(screen.queryByTestId("excess-table")).toBeNull();
    expect(screen.getByTestId("placebo").textContent).toBe("Placebo excess -3152, 95% interval -3368 to -2932");
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
  it("describes a records-based validation as a check of recorded closures, not of the street (REQ-STAT-VAL.5)", async () => {
    stub({ "validation.json": { data_version: V, status: "scored", method: "records", precision: { rate: 0.2, lo: 0.112, hi: 0.33, k: 10, n: 50 }, cant_tell_share: null, kappa: null, confirmed: ["a"], sample_ids: [],
      records: { checked_on: "2026-11-21", classes: { repaired_again: 21 }, ambiguous_ids: ["x", "y"], repaired_again_with_ambiguous: { rate: 0.42 } } } });
    open();
    const rec = await screen.findByTestId("validation-records");
    expect(rec.textContent).toContain("No one visited the sites.");
    expect(rec.textContent).toContain("as of 2026-11-21");
    expect(rec.textContent).toContain("Repaired again: 20.0%, 95% interval 11.2% to 33.0% (10 of 50)");
    expect(rec.textContent).toContain("up to 42.0%");
    expect(rec.textContent).toContain("2 closures are ambiguous");
    expect(rec.textContent).toContain("not conditions on the street");
    expect(screen.queryByTestId("validation-scored")).toBeNull();
  });
  it("says in the limits that the Skeptic reviewed only the highest-ranked candidates, so most cards have no second opinion (design review 5)", async () => {
    stub();
    open();
    expect((await screen.findByTestId("limit-skeptic")).textContent).toBe("The Skeptic reviewed only the highest-ranked candidates, so most cards have no second opinion.");
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
  it("shows the panel error, and no excess, shift or placebo claim, when the parser rejects the excess file (REQ-WEB-DATA.2, ops#100)", async () => {
    stub({ "excess.json": { ...(FILES["excess.json"] as object), placebo: { excess: "x" } } });  // the schema rejects a malformed placebo
    open();
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("excess.json");
    expect(screen.queryByTestId("excess-table")).toBeNull();
    expect(screen.queryByTestId("placebo")).toBeNull();
    expect(screen.queryByTestId("shift-range")).toBeNull();
    expect(screen.queryByText("The placebo result is not part of this data yet.")).toBeNull();
    expect(await screen.findByTestId("nightly-status")).toBeTruthy();
  });
  it("one failed file shows an error for its panel only", async () => {
    stub({}, ["excess.json"]);
    open();
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(await screen.findByTestId("nightly-status")).toBeTruthy();
  });
});

describe("Null towns, placebo and the floor (REQ-WEB-METHODS.1; ops#130)", () => {
  it("states plainly that no pretend town's interval lay above 0, with the counts, in copy that is not a placeholder", async () => {
    stub();
    open();
    const sum = await screen.findByTestId("null-summary");
    expect(sum.textContent).toContain("40 pretend towns");
    expect(sum.textContent).toContain("In none of them did the 95% interval for the excess lie above 0");
    expect(sum.textContent).toContain("below 0 in 32 towns and included 0 in 8");
    expect(sum.textContent).toContain("every placebo warning was below 0, never above");
    expect(sum.textContent).not.toMatch(/TODO-COPY/);
  });
  it("lists every pretend-town family with its range and where its interval fell", async () => {
    stub();
    open();
    const section = await screen.findByTestId("null-towns");
    const rows = within(section).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(10);
    const first = rows[0].textContent ?? "";
    expect(first).toContain("A report at each spot every 30 days on average");
    expect(within(section).queryByText("Random seeds")).toBeNull(); // UX-36: no seed column
    expect(first).not.toContain("5-8");
    expect(first).toContain("-855 to -643");
    expect(first).toContain("Below 0 in 4 of 4; includes 0 in 0");
    expect(rows[6].textContent).toContain("-34 to +16");
    expect(rows[6].textContent).toContain("Below 0 in 1 of 4; includes 0 in 3");
  });
  it("names the stress towns where the excess can read high, so the floor is not overstated", async () => {
    stub();
    open();
    const limits = await screen.findByTestId("null-limits");
    expect(limits.textContent).toContain("48 pretend towns");
    expect(limits.textContent).toContain("30 were not above 0 and 18 were above 0");
    expect(limits.textContent).toContain("the excess can read high");
  });
  it("calls the excess a floor and explains that the counts are a floor too", async () => {
    stub();
    open();
    const floor = await screen.findByTestId("excess-floor");
    expect(floor.textContent).toMatch(/Read the excess as a floor where reports arrive at a steady rate/);
    // UX-34: the condition sits in the same paragraph as the claim.
    expect(floor.textContent).toMatch(/bursts or stop partway through the data, the excess can read high/);
    expect(floor.textContent).toMatch(/pretend-town checks below/);
    expect(floor.textContent).not.toMatch(/TODO-COPY/);
    expect(floor.textContent).toMatch(/counts are also a floor/);
  });
  it("reads a placebo warning together with its sign: below 0 is cautious, above 0 is a care note, inside the interval has no note", async () => {
    const withPlacebo = (placebo: object) => ({ "excess.json": { ...(FILES["excess.json"] as object), placebo } });
    stub(withPlacebo({ excess: -60, lo: -90, hi: -30 }));
    const a = open();
    expect((await screen.findByTestId("placebo-note")).textContent).toContain("reads below 0 here. The baseline runs cautious");
    a.unmount(); clearDataCache();
    stub(withPlacebo({ excess: 70, lo: 40, hi: 100 }));
    const b = open();
    expect((await screen.findByTestId("placebo-note")).textContent).toContain("reads above 0 here");
    b.unmount(); clearDataCache();
    stub();
    open();
    await screen.findByTestId("placebo");
    expect(screen.queryByTestId("placebo-note")).toBeNull();
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
    expect(within(ex).getByText("Originals closed as transferred or migrated (legacy system) or as Transitioned (new system)").closest("tr")?.textContent).toContain("49");  // names both forms (ops#87)
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

describe("Methods page offers the sensitivity sliders (REQ-WEB-SLIDERS.1)", () => {
  it("shows the sliders on the methods page", async () => {
    stub();
    open();
    expect(await screen.findByTestId("sliders")).toBeTruthy();
    expect(await screen.findByTestId("slider-headline")).toBeTruthy();
  });

  it("builds a contents list from the page's own section headings, each linking to its section (REQ-WEB-METHODS.1)", async () => {
    stub();
    open();
    await screen.findByTestId("methods-intro", undefined, { timeout: 4000 });
    const toc = await screen.findByRole("navigation", { name: "On this page" });
    const links = await within(toc).findAllByRole("link", undefined, { timeout: 4000 });
    // the closed disclosure on a screen narrower than 70rem still holds the links in the document
    const headings = [...document.querySelectorAll(".methods-main h2")];
    expect(links.map((a) => a.textContent)).toEqual(headings.map((h) => h.textContent));
    for (const [i, a] of links.entries()) {
      expect(a.getAttribute("href")).toBe(`#${headings[i].id}`);
      expect(headings[i].id).toBeTruthy();
    }
    expect(new Set(headings.map((h) => h.id)).size).toBe(headings.length);
  });
  it("puts the page in one centred column, with a static contents list under the title, before the sections", async () => {
    stub();
    open();
    await screen.findByTestId("methods-intro", undefined, { timeout: 4000 });
    const main = document.querySelector(".methods-main") as HTMLElement;
    const toc = screen.getByRole("navigation", { name: "On this page" });
    expect(main.contains(toc)).toBe(true);
    expect(main.contains(screen.getByTestId("methods-intro"))).toBe(true);
    const h1 = main.querySelector("h1") as HTMLElement;
    expect(h1.compareDocumentPosition(toc) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(toc.compareDocumentPosition(main.querySelector("h2") as HTMLElement) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(toc.querySelector("details")).toBeNull(); // a plain list, never folded away
  });
});
