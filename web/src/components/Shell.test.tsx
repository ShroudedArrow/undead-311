import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { clearDataCache } from "../lib/data";

const STATUS = { data_version: "v", last_run: "2026-11-12T02:00:00Z", ok: true, row_counts: {}, anomalies: [], segments: "missing", data_end: "2026-11-11" };

afterEach(() => {
  vi.unstubAllGlobals();
  clearDataCache();
});

describe("Shell (REQ-WEB-DESIGN.3, REQ-WEB-FRESH.1)", () => {
  it("shows the independence line, OSM credit and data license, and the data date", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => STATUS }) as Response));
    render(
      <MemoryRouter>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByText("Independent project. Not affiliated with the City of Boston.")).toBeTruthy();
    expect(screen.getByText(/OpenStreetMap contributors/)).toBeTruthy();
    expect(screen.getByText(/Boston 311 service requests from Analyze Boston/)).toBeTruthy();
    expect(await screen.findByText("Data as of Nov 11, 2026")).toBeTruthy();
  });

  it("shows the unavailable label, not a crash, when status.json fails (REQ-WEB-DATA.2)", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 404, json: async () => ({}) }) as Response));
    render(
      <MemoryRouter>
        <App />
      </MemoryRouter>,
    );
    expect(await screen.findByText("Data date unavailable")).toBeTruthy();
    expect(screen.getByText("Independent project. Not affiliated with the City of Boston.")).toBeTruthy();
  });
});
