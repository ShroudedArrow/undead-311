import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
    open({ "repeat_offenders.json": ro, "status.json": read("status.json") });
    const table = await screen.findByTestId("repeat-table");
    // REQ-WEB-REPEAT.1, UX-43: the rule counts headline possible zombies, so the intro says so (times_risen counts every tier).
    expect(screen.getByText(/at least 3 possible zombies in the headline count in one chain/)).toBeTruthy();
    // REQ-WEB-REPEAT.1, design review 6: the table shows a first page of 25 rows and grows by 25 on request; the map and the count cover every chain.
    expect(within(table).getAllByRole("row").slice(1)).toHaveLength(Math.min(25, ro.repeat_offenders.length));
    if (ro.repeat_offenders.length > 25) await userEvent.click(screen.getByRole("button", { name: `Show ${Math.min(25, ro.repeat_offenders.length - 25)} more` }));
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(Math.min(50, ro.repeat_offenders.length));
    expect(screen.getByTestId("repeat-count").textContent).toBe(`${ro.repeat_offenders.length} chains`);
    // REQ-WEB-REPEAT.1, REQ-EXP-PRIV.1: each row's label follows its own chain's privacy level, whatever the data holds.
    const byId = new Map<string, { block_level: boolean }>(
      ro.repeat_offenders.map((c: { chain_id: string; block_level: boolean }) => [c.chain_id, c]),
    );
    for (const row of rows) {
      const chain = byId.get(row.getAttribute("data-chain") as string);
      expect(chain).toBeTruthy();
      const label = chain!.block_level ? "Shown at block level" : "Shown at the reported spot";
      expect(within(row).getByText(label)).toBeTruthy();
    }
    const first = rows[0];
    expect((await within(first).findByRole("link")).getAttribute("href")).toMatch(/^\/zombie\/\d+%3A\d+$/);
    expect((await screen.findByTestId("map")).getAttribute("data-count")).toBe(String(ro.repeat_offenders.length));
  });
  it("pages 25 rows at a time, keeps the rows shown and the sort in the URL, and re-sorts without losing the order of ties (design review 6)", async () => {
    const chain = (i: number) => ({ chain_id: `c${String(i).padStart(3, "0")}`, times_risen: 3 + (i % 4), headline_count: 3 + (i % 3), incident_ids: [`c${i}`], lat: 42.3, lon: -71.1, block_level: false, type_family: "sidewalk", neighborhood: i % 2 ? "Roxbury" : "Dorchester", first_zombie_id: `z${i}` });
    const ro = { data_version: "v", repeat_offenders: Array.from({ length: 60 }, (_, i) => chain(i)) };
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      const file = String(url).split("/").pop() as string;
      return { ok: file === "repeat_offenders.json", status: 200, json: async () => ro } as Response;
    }));
    const user = userEvent.setup();
    render(<MemoryRouter initialEntries={["/repeat?n=50&sort=where&dir=asc"]}><App /></MemoryRouter>);
    const table = await screen.findByTestId("repeat-table");
    expect(within(table).getAllByRole("row").slice(1)).toHaveLength(50);
    expect(screen.getByTestId("show-status").textContent).toBe("Showing 50 of 60");
    expect(within(table).getByRole("columnheader", { name: /Where/ }).getAttribute("aria-sort")).toBe("ascending");
    expect(within(table).getAllByRole("row")[1].getAttribute("data-chain")).toBe("c002"); // Dorchester first; within it the default order (most returns, most headline, chain ID)
    await user.click(screen.getByRole("button", { name: "Show 10 more" }));
    expect(within(table).getAllByRole("row").slice(1)).toHaveLength(60);
    expect(screen.queryByRole("button", { name: /Show .* more/ })).toBeNull();
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
    open({ "repeat_offenders.json": ro });
    expect(await screen.findByText("Shown at block level")).toBeTruthy();
  });
});
