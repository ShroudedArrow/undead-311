import { render, screen, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { clearDataCache } from "../lib/data";

vi.mock("../map/MapView", () => ({ default: (p: { rows: unknown[] }) => <div data-testid="map" data-count={p.rows.length} /> }));

const read = (f: string) => JSON.parse(readFileSync(join(__dirname, "..", "..", "public", "data", f), "utf8"));
function open(files: Record<string, unknown>) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const file = String(url).split("/").pop() as string;
    return { ok: file in files, status: file in files ? 200 : 404, json: async () => files[file] } as Response;
  }));
  return render(<MemoryRouter initialEntries={["/repeat"]}><App /></MemoryRouter>);
}
afterEach(() => { vi.unstubAllGlobals(); clearDataCache(); });

describe("Repeat offenders page (REQ-WEB-REPEAT.1)", () => {
  it("lists every exported chain with returns, headline count, how it is shown, and a link to its first card", async () => {
    const ro = read("repeat_offenders.json");
    open({ "repeat_offenders.json": ro, "zombies.json": read("zombies.json"), "status.json": read("status.json") });
    const table = await screen.findByTestId("repeat-table");
    // REQ-WEB-REPEAT.1, UX-43: the rule counts headline possible zombies, so the intro says so (times_risen counts every tier).
    expect(screen.getByText(/at least 3 possible zombies in the headline count in one chain/)).toBeTruthy();
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(ro.repeat_offenders.length);
    expect(screen.getByTestId("repeat-count").textContent).toBe(`${ro.repeat_offenders.length} chains`);
    const first = rows[0];
    expect(within(first).getByText("Shown at the reported spot")).toBeTruthy();
    expect((await within(first).findByRole("link")).getAttribute("href")).toMatch(/^\/zombie\/\d+%3A\d+$/);
    expect((await screen.findByTestId("map")).getAttribute("data-count")).toBe(String(ro.repeat_offenders.length));
  });
  it("says so when no chain reaches 3 headline possible zombies, and shows the panel error for a bad file", async () => {
    const { unmount } = open({ "repeat_offenders.json": { data_version: "v", repeat_offenders: [] } });
    expect(await screen.findByTestId("repeat-empty")).toBeTruthy();
    unmount();
    clearDataCache();
    open({ "repeat_offenders.json": { data_version: "v" } });
    expect(await screen.findByRole("alert")).toBeTruthy();
  });
  it("labels block-level chains", async () => {
    const ro = { data_version: "v", repeat_offenders: [{ chain_id: "c", times_risen: 4, headline_count: 3, incident_ids: ["c"], lat: 42.3, lon: -71.1, block_level: true, type_family: "sidewalk", neighborhood: "Dorchester" }] };
    open({ "repeat_offenders.json": ro, "zombies.json": { data_version: "v", zombies: [] } });
    expect(await screen.findByText("Shown at block level")).toBeTruthy();
  });
});
