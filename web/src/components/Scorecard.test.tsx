import fc from "fast-check";
import { render, screen, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { parseExcess, parseScorecard, type Scorecard as Sc, type ScorecardFile } from "../lib/parse";
import { headlineScorecards, pct, stayedFixedShown } from "../lib/rates";
import { ExcessLines, Scorecard } from "./Scorecard";
import type { ExcessFile, ExcessRow } from "../lib/parse";

const rate = (r: number, n = 100) => ({ rate: r, lo: Math.max(0, r - 0.05), hi: Math.min(1, r + 0.05), k: Math.round(r * n), n });
const sc = (family: string, adj: boolean, tier_set: "headline" | "all" = "headline"): Sc => ({
  family, tier_set, n_closed: 100, n_on_time_known: 100, on_time: rate(0.8), stayed_fixed_raw: rate(0.5), stayed_fixed_adj: adj ? rate(0.55) : null,
});
const file = (scorecards: Sc[]): ScorecardFile => ({ data_version: "v", scorecards, counts: { headline: 10, source_unknown: 2, city_rereport: 0, sensitivity: 1 }, params: { WINDOW_DAYS: 60, RADIUS_M: 30, matching: "segment" }, seed: null });

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
  it("writes the citywide group heading with a capital letter (UX-59, voice.md sentence case)", () => {
    render(<Scorecard file={file([sc("citywide", true), sc("sign", true)])} />);
    expect(screen.getByRole("heading", { name: "Citywide" })).toBeTruthy();
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
    const parsed = parseScorecard(JSON.parse(readFileSync(join(__dirname, "..", "..", "public", "data", "stats", "scorecard.json"), "utf8")));
    if (!parsed.ok) throw new Error(parsed.error);
    for (const s of parsed.data.scorecards) {
      expect(s.stayed_fixed_raw.rate as number).toBeLessThanOrEqual(s.on_time.rate as number);
      if (s.stayed_fixed_adj) expect(s.stayed_fixed_adj.rate as number).toBeLessThanOrEqual(s.on_time.rate as number);
    }
  });
});


const exRow = (over: Partial<ExcessRow> = {}): ExcessRow => ({
  kind: "family", name: "sign", tier_set: "headline", observed: 90, expected: 26.6, excess: 63.4, lo: 41.3, hi: 86, n_originals: 1504, n_bursty: 1479,
  without_bursty: { observed: 10, expected: 12.9, excess: -2.9, lo: -12.1, hi: 6.1, n_originals: 25 }, ...over,
});
const exFile = (rows: ExcessRow[]): ExcessFile => ({ data_version: "v", rows } as ExcessFile);

describe("Scorecard excess with and without bursty spots (REQ-STAT-BASE.2, REQ-WEB-SCORE.1, ops#130)", () => {
  it("shows both excess figures with intervals and the bursty share under each case type, and says it is not the headline", () => {
    render(<Scorecard file={file([sc("sign", true)])} excess={exFile([exRow()])} />);
    const row = screen.getByRole("heading", { name: "Signs" }).closest("li") as HTMLElement;
    expect(within(row).getByTestId("excess-all").textContent).toContain("excess of 63.4 re-reports (95% interval 41.3 to 86)");
    expect(within(row).getByTestId("excess-without").textContent).toContain("Without bursty spots: excess of -2.9 re-reports (95% interval -12.1 to 6.1)");
    expect(within(row).getByTestId("excess-without").textContent).toContain("from 25 closed cases");
    expect(within(row).getByTestId("excess-bursty").textContent).toContain("1479 of the 1504");
    expect(screen.getByText(/never the headline|A secondary check, never the headline/)).toBeTruthy();
  });
  it("says too few cases are left when no spot is left after removing bursty ones", () => {
    render(<ExcessLines row={exRow({ without_bursty: null })} />);
    expect(screen.getByTestId("excess-without").textContent).toBe("Without bursty spots: too few closed cases are left to say.");
  });
  it("shows nothing extra when the excess file has no row for the case type or is missing", () => {
    const { rerender } = render(<Scorecard file={file([sc("sign", true)])} excess={exFile([exRow({ name: "sidewalk" })])} />);
    expect(screen.queryByTestId("score-excess")).toBeNull();
    rerender(<Scorecard file={file([sc("sign", true)])} />);
    expect(screen.queryByTestId("score-excess")).toBeNull();
  });
  it("renders both lines for every case type in the exported excess file", () => {
    const ex = parseExcess(JSON.parse(readFileSync(join(__dirname, "..", "..", "public", "data", "stats", "excess.json"), "utf8")));
    const scf = parseScorecard(JSON.parse(readFileSync(join(__dirname, "..", "..", "public", "data", "stats", "scorecard.json"), "utf8")));
    if (!ex.ok || !scf.ok) throw new Error("exports do not parse");
    render(<Scorecard file={scf.data} excess={ex.data} />);
    expect(screen.getAllByTestId("excess-all").length).toBeGreaterThan(0);
    expect(screen.getAllByTestId("excess-without").length).toBe(screen.getAllByTestId("excess-all").length);
  });
  it("property: any finite row renders both lines without throwing", () => {
    const n = fc.double({ min: -1000, max: 1000, noNaN: true });
    fc.assert(
      fc.property(n, n, n, fc.nat(5000), fc.boolean(), (a, b, c, k, none) => {
        const { unmount } = render(<ExcessLines row={exRow({ excess: a, lo: Math.min(a, b), hi: Math.max(a, c), n_originals: k, n_bursty: Math.min(k, 7), without_bursty: none ? null : { observed: 1, expected: 2, excess: b, lo: b - 1, hi: b + 1, n_originals: k } })} />);
        const ok = screen.getByTestId("excess-all").textContent !== "" && screen.getByTestId("excess-without").textContent !== "";
        unmount();
        return ok;
      }),
      { numRuns: 40 },
    );
  });
});
