import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { clearDataCache } from "../lib/data";

vi.mock("../map/MapView", () => ({ default: () => <div data-testid="map" /> }));

const rec = (id: string) => ({ id, system: "legacy", open_time: "2026-01-10T15:00:00Z", close_time: "2026-01-12T15:00:00Z", type_raw: "Pothole", status: "Closed", closure_text: "done", street: "Main St", lat: 42.3, lon: -71.05 });
const POINTS = { data_version: "v", n: 1, id: ["z1"], lat: [42.3], lon: [-71], tier: ["headline"], family: ["sign"], department: [null], neighborhood: ["Dorchester"], year: [2026] };
const SHARD = { data_version: "v", shard: "dorchester-2026", cards: [{ zombie_id: "z1", original: rec("o"), rereport: rec("r"), cause_of_death: "resolved", gap_days: 3, resurrection_date: "2026-01-20", confidence: 0.8, tier: "headline", skeptic_verdict: "survives", skeptic_notes: "note", bulk_closure: false }] };

function open(version: string) {
  const status = { data_version: version, last_run: "2026-11-11T00:00:00Z", ok: true, row_counts: {}, anomalies: [], segments: "missing" };
  vi.stubGlobal("matchMedia", (q: string) => ({ matches: false, addEventListener() {}, removeEventListener() {}, media: q }));
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const u = String(url);
    const body = u.endsWith("points.json") ? POINTS : u.includes("cards/") ? SHARD : status;
    return { ok: true, status: 200, json: async () => body } as Response;
  }));
  render(<MemoryRouter initialEntries={["/zombie/z1"]}><App /></MemoryRouter>);
}

afterEach(() => { vi.unstubAllGlobals(); clearDataCache(); });

describe("the card repeats the preview notice for fixture data (REQ-WEB-DATA.3, REQ-WEB-CARD.5, UX-13)", () => {
  it("shows a short notice inside the card when the data is a fixture", async () => {
    open("fixture-2026-11-11");
    await screen.findByText(/Autopsy report/);
    expect(await screen.findByTestId("card-fixture-notice")).toBeTruthy();
  });

  it("shows no notice inside the card for real data", async () => {
    open("2026-11-11");
    await screen.findByText(/Autopsy report/);
    await screen.findByText("Data as of Nov 11, 2026");
    expect(screen.queryByTestId("card-fixture-notice")).toBeNull();
  });
});
