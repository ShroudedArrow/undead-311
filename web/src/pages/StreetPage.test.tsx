import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { clearDataCache } from "../lib/data";

vi.mock("../map/MapView", () => ({ default: (p: { rows: unknown[]; bounds: unknown }) => <div data-testid="map" data-count={p.rows.length} data-bounds={JSON.stringify(p.bounds)} /> }));
vi.mock("../generated/streets.json", () => ({
  default: { source: "cases", streets: [
    { k: "COMMONWEALTH AVE", n: "Commonwealth Ave", p: [[42.35, -71.1], [42.351, -71.1]] },
    { k: "EMPTY ST", n: "Empty St", p: [[42.2, -71.0]] },
  ] },
}));

const POINTS = { data_version: "v", n: 2, id: ["z1", "z2"], lat: [42.3501, 42.3509], lon: [-71.1, -71.1], tier: ["headline", "headline"], family: ["sign", "sidewalk"], department: [null, null], neighborhood: ["Back Bay", "Back Bay"], year: [2024, 2025] };
const GRID = { data_version: "v", params: { WINDOW_DAYS: 60, RADIUS_M: 30, matching: "segment" }, points: [60, 90].map((w) => ({ matching: "segment", radius_m: 30, window_days: w, headline: w === 60 ? 10 : 14, source_unknown: 0, city_rereport: 0, sensitivity: 0, excess: 1, stayed_fixed_rate: 0.5 })), without_street_light_other: { headline: 1, all_tiers: 1 } };
const STATUS = { data_version: "v", last_run: "2026-11-11T00:00:00Z", ok: true, row_counts: {}, anomalies: [], segments: "missing" };

function open(path = "/street") {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const u = String(url);
    const body = u.endsWith("points.json") ? POINTS : u.endsWith("sensitivity_grid.json") ? GRID : STATUS;
    return { ok: true, status: 200, json: async () => body } as Response;
  }));
  return render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>);
}
afterEach(() => { vi.unstubAllGlobals(); clearDataCache(); });

describe("Check my street (REQ-WEB-STREET.1)", () => {
  it("searches the street list, zooms to the street and lists nearby possible zombies", async () => {
    open();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Street name"), "commonwealth avenue");
    await user.click(screen.getByRole("button", { name: "Commonwealth Ave" }));
    const result = await screen.findByTestId("street-result");
    await waitFor(() => expect(within(result).getByTestId("street-count").textContent).toContain("2 found"));
    expect(within(result).getAllByRole("link").map((a) => a.getAttribute("href"))).toEqual(["/zombie/z1", "/zombie/z2"]);
    expect((await within(result).findByTestId("map")).getAttribute("data-bounds")).toBe("[-71.1,42.35,-71.1,42.351]");
  });
  it("shows the empty state with a wider search and the 90-day count when nothing is near", async () => {
    open("/street?s=EMPTY%20ST");
    const empty = await screen.findByTestId("street-empty");
    expect(empty.textContent).toContain("TODO-COPY");
    expect(empty.textContent).toContain("14 headline possible zombies across Boston, against 10 with the 60-day window");
    fireEvent.click(screen.getByRole("button", { name: "Search within 300 meters instead" }));
    expect(await screen.findByRole("button", { name: "Search within 600 meters instead" })).toBeTruthy();
  });
  it("says so when no street matches, and notes the list holds only streets with cases", async () => {
    open();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Street name"), "qqqq");
    expect(screen.getByTestId("street-no-match")).toBeTruthy();
    expect(screen.getByText(/holds only streets that appear in a case record/)).toBeTruthy();
  });
  it("opens straight to a street from a link", async () => {
    open("/street?s=COMMONWEALTH%20AVE&r=300");
    expect(await screen.findByRole("heading", { name: "Possible zombies within 300 meters of Commonwealth Ave" })).toBeTruthy();
  });
});
