import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { clearDataCache } from "../lib/data";
import { sampleCaseCount } from "../lib/dataAsOf";
import { t } from "../lib/t";
import { AutopsyCard, type CardWithPartial } from "./AutopsyCard";

vi.mock("../map/MapView", () => ({ default: () => <div data-testid="map" /> }));

const STATUS = { data_version: "v", last_run: "2026-11-12T02:00:00Z", ok: true, row_counts: { sample_rows: 15361 }, anomalies: [], segments: "missing", data_end: "2026-11-11" };
function serve(status: unknown) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const file = String(url).split("/").pop() as string;
    return { ok: file === "status.json", status: file === "status.json" ? 200 : 404, json: async () => (file === "status.json" ? status : {}) } as Response;
  }));
}
afterEach(() => { vi.unstubAllGlobals(); clearDataCache(); });

describe("sample notice (REQ-WEB-FRESH.1, ops#216)", () => {
  it("counts sample rows only for a sample run", () => {
    expect(sampleCaseCount({ dataset: "sample", row_counts: { sample_rows: 15361 } })).toBe(15361);
    expect(sampleCaseCount({ dataset: "sample", row_counts: { in_scope_cases: 12 } })).toBe(12);
    expect(sampleCaseCount({ dataset: "full", row_counts: { sample_rows: 15361 } })).toBeNull();
    expect(sampleCaseCount({ row_counts: {} })).toBeNull();
    expect(sampleCaseCount(null)).toBeNull();
  });
  it("shows the notice next to the date on every page and on the methods page for a sample run", async () => {
    serve({ ...STATUS, dataset: "sample" });
    const { unmount } = render(<MemoryRouter initialEntries={["/methods"]}><App /></MemoryRouter>);
    expect((await screen.findByTestId("sample-notice")).textContent).toBe("Sample of 15,361 cases, not all of Boston.");
    expect((await screen.findByTestId("methods-sample-notice")).textContent).toContain("15,361 cases");
    unmount();
    clearDataCache();
    serve({ ...STATUS, dataset: "sample" });
    render(<MemoryRouter initialEntries={["/"]}><App /></MemoryRouter>);
    expect(await screen.findByTestId("sample-notice")).toBeTruthy();
  });
  it("hides both notices for a full-data run", async () => {
    serve({ ...STATUS, dataset: "full" });
    render(<MemoryRouter initialEntries={["/methods"]}><App /></MemoryRouter>);
    await screen.findByText("Data as of Nov 11, 2026");
    expect(screen.queryByTestId("sample-notice")).toBeNull();
    expect(screen.queryByTestId("methods-sample-notice")).toBeNull();
  });
});

const CARD: CardWithPartial = {
  zombie_id: "I-1:2",
  original: { id: "101001", system: "legacy", open_time: "2026-01-10T15:00:00Z", close_time: "2026-01-12T15:00:00Z", type_raw: "Request for Pothole Repair", status: "Closed", closure_text: "Case Resolved", street: "Call St & Carolina Ave", lat: 42.3, lon: -71.05 },
  rereport: { id: "BCS-2", system: "new", open_time: "2026-01-20T15:00:00Z", close_time: null, type_raw: "Pothole", status: "Open", closure_text: null, street: "Call St & Carolina Ave", lat: 42.3, lon: -71.05 },
  cause_of_death: "resolved", gap_days: 8, resurrection_date: "2026-01-20", confidence: 0.7, tier: "headline",
  skeptic_verdict: "not_reviewed", skeptic_notes: "", reports_after: 1, times_risen: 1, bulk_closure: false,
};

describe("Skeptic section (REQ-WEB-CARD.1, ops#217)", () => {
  it("an unreviewed card shows only the not-reviewed verdict, never 'No objections recorded.'", () => {
    render(<AutopsyCard card={CARD} />);
    const card = screen.getByTestId("autopsy-card");
    expect(within(card).queryByText(t("card.no_notes"))).toBeNull();
    expect(within(card).getByText(t("card.verdict_not_reviewed"))).toBeTruthy();
  });
  it("a reviewed card with no notes still says 'No objections recorded.'", () => {
    render(<AutopsyCard card={{ ...CARD, skeptic_verdict: "survives" }} />);
    expect(within(screen.getByTestId("autopsy-card")).getByText(t("card.no_notes"))).toBeTruthy();
  });
  it("shows an '&' street name as plain '&' (ops#214)", () => {
    render(<AutopsyCard card={CARD} />);
    expect(within(screen.getByTestId("autopsy-card")).getAllByText(/Call St & Carolina Ave/).length).toBeGreaterThan(0);
  });
});

describe("not-found page (ops#219)", () => {
  it("has a heading and a link back to the map", async () => {
    serve(STATUS);
    render(<MemoryRouter initialEntries={["/no-such-page"]}><App /></MemoryRouter>);
    const page = await screen.findByTestId("not-found");
    expect(within(page).getByRole("heading", { level: 1, name: "Page not found" })).toBeTruthy();
    expect(within(page).getByRole("link", { name: "Go back to the map" }).getAttribute("href")).toBe("/");
  });
});
