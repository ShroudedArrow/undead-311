import fc from "fast-check";
import { render, screen, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { parseScorecard, type Scorecard as Sc, type ScorecardFile } from "../lib/parse";
import { headlineScorecards, pct, stayedFixedShown } from "../lib/rates";
import { Scorecard } from "./Scorecard";

const rate = (r: number, n = 100) => ({ rate: r, lo: Math.max(0, r - 0.05), hi: Math.min(1, r + 0.05), k: Math.round(r * n), n });
const sc = (family: string, adj: boolean, tier_set: "headline" | "all" = "headline"): Sc => ({
  family, tier_set, n_closed: 100, n_on_time_known: 100, on_time: rate(0.8), stayed_fixed_raw: rate(0.5), stayed_fixed_adj: adj ? rate(0.55) : null,
});
const file = (scorecards: Sc[]): ScorecardFile => ({ data_version: "v", scorecards, counts: { headline: 10, source_unknown: 2, sensitivity: 1 }, params: { WINDOW_DAYS: 60, RADIUS_M: 30, matching: "segment" }, seed: null });

describe("Scorecard (REQ-WEB-SCORE.1-2)", () => {
  it("shows on-time and stayed-fixed side by side, each with interval and n", () => {
    render(<Scorecard file={file([sc("sign", true)])} />);
    const row = screen.getByRole("heading", { name: "Signs" }).closest("li") as HTMLElement;
    expect(within(row).getByText("Closed on time")).toBeTruthy();
    expect(within(row).getByText("80.0%")).toBeTruthy();
    expect(within(row).getAllByText("95% interval 75.0% to 85.0%").length).toBe(1);
    expect(within(row).getAllByText("n = 100").length).toBe(2);
  });
  it("shows the adjusted rate as the stayed-fixed number, labelled, with the raw rate in a detail view", () => {
    render(<Scorecard file={file([sc("sign", true)])} />);
    expect(screen.getByText("Stayed fixed (adjusted)")).toBeTruthy();
    expect(screen.getByText("55.0%")).toBeTruthy();
    expect(screen.getByText("Show the raw rate")).toBeTruthy();
    expect(screen.getByText(/Raw stayed-fixed rate: 50.0%/)).toBeTruthy();
  });
  it("shows the raw rate, labelled raw, when no adjusted rate exists", () => {
    render(<Scorecard file={file([sc("sign", false)])} />);
    expect(screen.getByText("Stayed fixed (raw)")).toBeTruthy();
    expect(screen.queryByText("Show the raw rate")).toBeNull();
  });
  it("says there are not enough cases when the rate is null", () => {
    const s = sc("sign", false);
    s.on_time = { rate: null, lo: null, hi: null, n: 0, reason: "no cases" };
    render(<Scorecard file={file([s])} />);
    expect(screen.getByText("Not enough cases for a rate.")).toBeTruthy();
  });
  it("lists citywide first and only headline sets", () => {
    const rows = headlineScorecards([sc("sign", true), sc("all", true), sc("sidewalk", true), sc("sign", true, "all")]);
    expect(rows.map((r) => r.family)).toEqual(["all", "sidewalk", "sign"]);
  });
  it("picks adjusted whenever it exists", () => {
    fc.assert(fc.property(fc.boolean(), (adj) => {
      expect(stayedFixedShown(sc("sign", adj)).kind).toBe(adj ? "adjusted" : "raw");
    }));
  });
  it("formats percentages within 0 to 100 for any rate in [0, 1]", () => {
    fc.assert(fc.property(fc.double({ min: 0, max: 1, noNaN: true }), (r) => {
      const v = parseFloat(pct(r));
      expect(v).toBeGreaterThanOrEqual(0);
      expect(v).toBeLessThanOrEqual(100);
    }));
  });
});

describe("fixture scorecard (REQ-WEB-DATA.3, testing.md #10, #17)", () => {
  it("has stayed-fixed at or below on-time, raw and adjusted", () => {
    const parsed = parseScorecard(JSON.parse(readFileSync(join(__dirname, "..", "..", "public", "data", "scorecard.json"), "utf8")));
    if (!parsed.ok) throw new Error(parsed.error);
    for (const s of parsed.data.scorecards) {
      expect(s.stayed_fixed_raw.rate as number).toBeLessThanOrEqual(s.on_time.rate as number);
      if (s.stayed_fixed_adj) expect(s.stayed_fixed_adj.rate as number).toBeLessThanOrEqual(s.on_time.rate as number);
    }
  });
});
