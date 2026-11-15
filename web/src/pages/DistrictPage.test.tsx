import { render, screen, within } from "@testing-library/react";
import { fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { clearDataCache } from "../lib/data";

const Z = { after_temporary_fix: false, baseline_p: 0, bulk_closure: false, chain_id: "c", city_rereport: false, close_year: 2015, confidence: 0.8, confidence_partial: false, coroner_label: "resolved", department: null, distance_m: 0, district: "3", gap_days: 3, incident_id: "i", is_planned_followup: false, match_mode: "segment", neighborhood: "Dorchester", reports_after: 1, resurrection_id: "r", segment_id: null, skeptic_notes: "", skeptic_verdict: "not_reviewed", source_unknown: false, tier: "headline", times_risen: 1, type_family: "sign", resurrection_date: "2020-05-01" };
const withDistrict = { data_version: "v", zombies: [{ ...Z, zombie_id: "1" }, { ...Z, zombie_id: "2", type_family: "sidewalk" }, { ...Z, zombie_id: "3", district: null }] };
const noDistrict = { data_version: "v", zombies: [{ ...Z, zombie_id: "1", district: null }] };

function open(path: string, zombies: unknown) {
  vi.stubGlobal("fetch", vi.fn(async (u: string) => ({ ok: true, status: 200, headers: new Headers(), json: async () => (String(u).endsWith("zombies.json") ? zombies : { data_version: "v", last_run: "2026-11-11T00:00:00Z", ok: true, row_counts: {}, anomalies: [], segments: "missing" }) }) as Response));
  return render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>);
}
afterEach(() => { vi.unstubAllGlobals(); clearDataCache(); });

describe("District report cards (REQ-WEB-OPEN.2)", () => {
  it("lists districts and opens one printable card with counts by case type and year", async () => {
    open("/districts", withDistrict);
    const list = await screen.findByTestId("district-list");
    expect(within(list).getByRole("link", { name: "3" }).getAttribute("href")).toBe("/districts/3");
    expect(within(list).getAllByRole("row")[1].textContent).toBe("32");
  });
  it("shows the card for a district with a print button, the print-only source line, and says rates are not exported yet", async () => {
    open("/districts/3", withDistrict);
    const card = await screen.findByTestId("district-card");
    expect(within(card).getByRole("heading", { level: 1 }).textContent).toBe("Report card for council district 3");
    expect(within(card).getByText("2 headline possible zombies")).toBeTruthy();
    expect(within(card).getByText("Sidewalks")).toBeTruthy();
    expect(within(card).getByText(/not part of this data yet/)).toBeTruthy();
    const print = vi.fn();
    vi.stubGlobal("print", print);
    fireEvent.click(within(card).getByRole("button", { name: "Print this page" }));
    expect(print).toHaveBeenCalled();
    expect(card.querySelector(".print-only")?.textContent).toContain("Not affiliated with the City of Boston");
  });
  it("says so when no district is recorded, or the district is unknown", async () => {
    const { unmount } = open("/districts", noDistrict);
    expect(await screen.findByTestId("district-none")).toBeTruthy();
    unmount();
    clearDataCache();
    open("/districts/99", withDistrict);
    expect(await screen.findByTestId("district-not-found")).toBeTruthy();
  });
});

describe("Open data on the methods page (REQ-WEB-OPEN.1, .3)", () => {
  it("links JSON, makes the CSV on request, and shows the license placeholder and the before/after note", async () => {
    const created: Blob[] = [];
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: (b: Blob) => { created.push(b); return "blob:x"; }, revokeObjectURL: () => undefined }));
    open("/methods", withDistrict);
    const section = await screen.findByTestId("open-data");
    expect(within(section).getByRole("link", { name: "Download as JSON" }).getAttribute("href")).toBe("/data/zombies.json");
    expect(within(section).getByTestId("open-license-dataset").textContent).toMatch(/^TODO-COPY:/);
    expect(within(section).getByTestId("before-after-note").textContent).toContain("format changes can create artifacts");
    fireEvent.click(within(section).getByRole("button", { name: "Download as CSV" }));
    await waitFor(() => expect(within(section).getByText("3 rows, one per possible zombie.")).toBeTruthy());
    fireEvent.click(within(section).getByRole("button", { name: "Download as CSV" }));
    expect(created).toHaveLength(1);
    expect(await created[0].text()).toContain("zombie_id,tier");
  });
});
