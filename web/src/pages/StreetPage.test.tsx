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
    expect(empty.textContent).toContain("No possible zombies on this block in the last 60 days. Try widening the window to 90 days.");
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

describe("Check my street: long result lists (design review 6)", () => {
  function openMany(count: number, path: string) {
    const n = Array.from({ length: count }, (_, i) => i);
    const points = { data_version: "v", n: count, id: n.map((i) => `z${String(i).padStart(3, "0")}`), lat: n.map((i) => 42.3501 + i * 0.000001), lon: n.map(() => -71.1), tier: n.map(() => "headline"), family: n.map(() => "sign"), department: n.map(() => null), neighborhood: n.map(() => "Back Bay"), year: n.map(() => 2024) };
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      const u = String(url);
      const body = u.endsWith("points.json") ? points : u.endsWith("sensitivity_grid.json") ? GRID : STATUS;
      return { ok: true, status: 200, json: async () => body } as Response;
    }));
    return render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>);
  }
  it("lists 25 results first, adds 25 per press, and keeps the count in the address", async () => {
    openMany(60, "/street?s=COMMONWEALTH%20AVE");
    const user = userEvent.setup();
    const result = await screen.findByTestId("street-result");
    await waitFor(() => expect(within(result).getAllByRole("link")).toHaveLength(25));
    expect(within(result).getByTestId("street-count").textContent).toContain("60 found");
    expect(within(result).getByTestId("show-status").textContent).toBe("Showing 25 of 60");
    await user.click(within(result).getByRole("button", { name: "Show 25 more" }));
    expect(within(result).getAllByRole("link")).toHaveLength(50);
    await user.click(within(result).getByRole("button", { name: "Show 10 more" }));
    expect(within(result).getAllByRole("link")).toHaveLength(60);
    expect(within(result).queryByRole("button", { name: /Show .* more/ })).toBeNull();
  });
  it("opens at the number of rows the address names, and shows no button for a short list", async () => {
    openMany(60, "/street?s=COMMONWEALTH%20AVE&n=50");
    const result = await screen.findByTestId("street-result");
    await waitFor(() => expect(within(result).getAllByRole("link")).toHaveLength(50));
    expect(within(result).getByTestId("show-status").textContent).toBe("Showing 50 of 60");
  });
  it("shows no paging line when 25 or fewer are found", async () => {
    openMany(12, "/street?s=COMMONWEALTH%20AVE");
    const result = await screen.findByTestId("street-result");
    await waitFor(() => expect(within(result).getAllByRole("link")).toHaveLength(12));
    expect(within(result).queryByTestId("show-status")).toBeNull();
  });
});
