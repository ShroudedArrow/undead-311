import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { clearDataCache } from "../lib/data";

const times = Array.from({ length: 91 }, (_, i) => i);
const curve = (name: string, tier_set: "headline" | "all", drop: number) => ({
  name, tier_set, times, survival: times.map((d) => 1 - (drop * d) / 90), lo: times.map((d) => Math.max(0, 1 - (drop * d) / 90 - 0.02)), hi: times.map((d) => Math.min(1, 1 - (drop * d) / 90 + 0.02)),
  at_7: 0.99, at_30: 0.95, at_90: 1 - drop, half_life: null,
});
const SURVIVAL = { data_version: "v", curves: [curve("all", "headline", 0.1), curve("family:sign", "headline", 0.3), curve("department:PWDx", "headline", 0.2), curve("all", "all", 0.12), curve("family:sign", "all", 0.35)] };
const limits = [1, 10, 100, 1000].map((n) => ({ n, lo95: 0.05, hi95: 0.2, lo998: 0.02, hi998: 0.3 }));
const g = (name: string, raw: number, shrunk: number, unusual: boolean, kind = "neighborhood") => ({ kind, name, n: 100, k: Math.round(raw * 100), raw, shrunk, lo: shrunk - 0.03, hi: shrunk + 0.03, unusual, reports_per_km: null });
const GROUPS = [g("Roxbury", 0.5, 0.3, true), g("Dorchester", 0.12, 0.11, false), g("Hyde Park", 0.01, 0.05, true), g("sign", 0.1, 0.1, false, "family")];
const FUNNEL = { data_version: "v", citywide: 0.1, limits, groups: GROUPS };
const GROUPS_FILE = { data_version: "v", citywide: 0.1, kappa: 40, groups: GROUPS };

function stub(missing: string[] = []) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const u = String(url);
    const file = u.split("/").pop() as string;
    if (missing.includes(file)) return { ok: false, status: 404, json: async () => ({}) } as Response;
    const body = file === "survival.json" ? SURVIVAL : file === "funnel.json" ? FUNNEL : file === "groups.json" ? GROUPS_FILE : { data_version: "v", last_run: "2026-11-11T00:00:00Z", ok: true, row_counts: {}, anomalies: [], segments: "missing" };
    return { ok: true, status: 200, json: async () => body } as Response;
  }));
}
afterEach(() => { vi.unstubAllGlobals(); clearDataCache(); });

const open = () => render(<MemoryRouter initialEntries={["/durability"]}><App /></MemoryRouter>);

describe("Durability page: survival (REQ-WEB-CHARTS.1)", () => {
  it("draws the citywide curve with its interval band, and a table with 7, 30 and 90 days and the half-life", async () => {
    stub();
    open();
    expect(await screen.findByTestId("survival-chart", undefined, { timeout: 4000 })).toBeTruthy();
    expect(screen.getByTestId("survival-band")).toBeTruthy();
    const table = screen.getByTestId("survival-table");
    expect(within(table).getByText("At 7 days")).toBeTruthy();
    expect(within(table).getByText("At 30 days")).toBeTruthy();
    expect(within(table).getByText("At 90 days")).toBeTruthy();
    // design review 8: a half-life column that says the same in every row is left out, with one sentence under the table
    expect(within(table).queryByText("Half-life")).toBeNull();
    expect(screen.getByTestId("half-life-note").textContent).toMatch(/still above 50% at day 90/);
    expect(within(table).getByText(/99\.0% \(97\.2% to 100\.0%\)/)).toBeTruthy();
  });
  it("shows a picked group against the citywide curve and switches to all tiers", async () => {
    stub();
    const user = userEvent.setup();
    open();
    await screen.findByTestId("survival-chart", undefined, { timeout: 4000 });
    await user.selectOptions(screen.getByLabelText("Show against the citywide curve"), "family:sign");
    expect(screen.getByTestId("survival-chart").getAttribute("aria-label")).toContain("Signs");
    expect(within(screen.getByTestId("survival-table")).getAllByRole("row")).toHaveLength(3);
    await user.click(screen.getByLabelText("All tiers"));
    expect((screen.getByLabelText("Show against the citywide curve") as HTMLSelectElement).value).toBe("");
    expect(screen.getByTestId("survival-chart").getAttribute("aria-label")).toContain("All tiers");
  });
});

describe("Durability page: survival legend and ticks (REQ-WEB-CHARTS.1, UX-22)", () => {
  it("names the solid line, the dashed citywide line and the band, and both curves in the aria-label", async () => {
    stub();
    const user = userEvent.setup();
    open();
    await screen.findByTestId("survival-chart", undefined, { timeout: 4000 });
    const legend = screen.getByTestId("survival-legend");
    expect(within(legend).getAllByRole("listitem")).toHaveLength(2);
    expect(within(legend).getByText("95% interval")).toBeTruthy();
    await user.selectOptions(screen.getByLabelText("Show against the citywide curve"), "family:sign");
    expect(within(screen.getByTestId("survival-legend")).getAllByRole("listitem")).toHaveLength(3);
    expect(within(screen.getByTestId("survival-legend")).getByText("Citywide")).toBeTruthy();
    const label = screen.getByTestId("survival-chart").getAttribute("aria-label") ?? "";
    expect(label).toContain("Signs");
    expect(label).toContain("Dashed line for Citywide");
  });
  it("puts y ticks on whole or 5% steps", async () => {
    stub();
    open();
    const chart = await screen.findByTestId("survival-chart", undefined, { timeout: 4000 });
    const ticks = [...chart.querySelectorAll("text.chart-tick")].map((n) => n.textContent ?? "").filter((x) => x.endsWith("%"));
    expect(ticks.length).toBeGreaterThan(1);
    for (const tick of ticks) expect(Number.parseFloat(tick) % 5, tick).toBe(0);
  });
});

describe("Durability page: funnel and leaderboard (REQ-WEB-CHARTS.2)", () => {
  it("calls a group unusual only in the table when it is outside the 99.8% limits, and says so in words", async () => {
    stub();
    open();
    const board = await screen.findByTestId("leaderboard", undefined, { timeout: 4000 });
    const rows = within(board).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(3);
    expect(rows[0].textContent).toContain("Roxbury");
    expect(rows[0].textContent).toContain("Above the 99.8% limits");
    expect(rows[1].textContent).toContain("Within the limits");
    expect(rows[2].textContent).toContain("Hyde Park");
    expect(rows[2].textContent).toContain("Below the 99.8% limits");
    expect(screen.getByTestId("funnel-chart").getAttribute("aria-label")).toContain("1 groups lie above the 99.8% limits and 1 below them");
  });
  it("marks a group below the limits with a dark square, never pink, and the legend names both directions (REQ-WEB-CHARTS.2, UX-17)", async () => {
    stub();
    open();
    const chart = await screen.findByTestId("funnel-chart", undefined, { timeout: 4000 });
    expect(chart.querySelectorAll("polygon.funnel-above")).toHaveLength(1);
    const below = chart.querySelectorAll("rect.funnel-below");
    expect(below).toHaveLength(1);
    expect(below[0].querySelector("title")?.textContent).toBe("Hyde Park: 1.0%, n = 100 (below the 99.8% limits)");
    expect(screen.getByText("Above the 99.8% limits (pink diamond)")).toBeTruthy();
    expect(screen.getByText("Below the 99.8% limits (dark square)")).toBeTruthy();
  });
  it("shows reporting intensity beside every neighborhood rate, and says when it is missing", async () => {
    stub();
    open();
    const board = await screen.findByTestId("leaderboard", undefined, { timeout: 4000 });
    // design review 8: with no intensity value anywhere the column is left out, instead of "Not available" on every row
    expect(within(board).queryByText("Not available in this data")).toBeNull();
    expect(within(board).queryByText("Reporting intensity")).toBeNull();
    expect(screen.getByText(/Reporting intensity sits beside every neighborhood rate/)).toBeTruthy();
  });
  it("keeps the raw rate and n beside the shrunk rate", async () => {
    stub();
    open();
    const board = await screen.findByTestId("leaderboard", undefined, { timeout: 4000 });
    for (const h of ["Shrunk rate", "Raw rate", "Closed cases (n)", "95% interval"]) expect(within(board).getByText(h)).toBeTruthy();
  });
  it("shows an error for one panel and keeps the other (REQ-WEB-DATA.2)", async () => {
    stub(["survival.json"]);
    open();
    expect(await screen.findByRole("alert", undefined, { timeout: 4000 })).toBeTruthy();
    expect(await screen.findByTestId("leaderboard", undefined, { timeout: 4000 })).toBeTruthy();
  });
});
