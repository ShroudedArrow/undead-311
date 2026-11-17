import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { clearDataCache } from "../lib/data";

vi.mock("../map/MapView", () => ({ default: (p: { rows: unknown[] }) => <div data-testid="map" data-count={p.rows.length} /> }));

const IDS = ["z1", "z2", "z3", "z4"];
const DATES = ["2016-01-10", "2018-06-01", "2018-09-09", "2024-02-02"];
const POINTS = { data_version: "v", n: 4, id: IDS, lat: IDS.map(() => 42.3), lon: IDS.map(() => -71), tier: IDS.map(() => "headline"), family: IDS.map(() => "sign"), department: IDS.map(() => null), neighborhood: IDS.map(() => "Dorchester"), year: [2016, 2018, 2018, 2024], date: DATES };

function open(reduced = false, points: unknown = POINTS) {
  vi.stubGlobal("matchMedia", (q: string) => ({ matches: reduced && q.includes("reduce"), addEventListener() {}, removeEventListener() {}, media: q }));
  vi.stubGlobal("fetch", vi.fn(async (u: string) => ({ ok: true, status: 200, headers: new Headers(), json: async () => (String(u).endsWith("points.json") ? points : { data_version: "v", last_run: "2026-11-11T00:00:00Z", ok: true, row_counts: {}, anomalies: [], segments: "missing" }) }) as Response));
  return render(<MemoryRouter initialEntries={["/timelapse"]}><App /></MemoryRouter>);
}
beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true, toFake: ["performance", "requestAnimationFrame", "cancelAnimationFrame", "setTimeout", "clearTimeout"] }));
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); clearDataCache(); });

describe("Night of the Living 311 (REQ-WEB-TIMELAPSE.1)", () => {
  it("does not move until play is pressed, then adds possible zombies as time passes and ends on all of them", async () => {
    open();
    expect((await screen.findByTestId("timelapse-now")).textContent).toContain("4 of 4");
    fireEvent.click(screen.getByRole("button", { name: "Play the time-lapse" }));
    expect(screen.getByTestId("timelapse-now").textContent).toContain("1 of 4");
    await act(async () => { await vi.advanceTimersByTimeAsync(30_000); });
    expect(screen.getByTestId("timelapse-now").textContent).toContain("4 of 4");
    expect(screen.getByRole("button", { name: "Play again" })).toBeTruthy();
  });
  it("can be paused, scrubbed and skipped to the end", async () => {
    open();
    await screen.findByTestId("timelapse-now");
    fireEvent.click(screen.getByRole("button", { name: "Play the time-lapse" }));
    fireEvent.click(screen.getByRole("button", { name: "Pause" }));
    expect(screen.getByRole("button", { name: "Resume" })).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Date shown"), { target: { value: "500" } });
    const mid = screen.getByTestId("map").getAttribute("data-count");
    expect(Number(mid)).toBeGreaterThanOrEqual(1);
    expect(Number(mid)).toBeLessThan(4);
    fireEvent.click(screen.getByRole("button", { name: "Skip to the end" }));
    expect(screen.getByTestId("map").getAttribute("data-count")).toBe("4");
  });
  it("under reduced motion there is no play button: every point is shown with a table of counts per year", async () => {
    open(true);
    expect(await screen.findByTestId("reduced-note")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Play the time-lapse" })).toBeNull();
    expect(screen.getByTestId("map").getAttribute("data-count")).toBe("4");
    const rows = within(screen.getByTestId("year-table")).getAllByRole("row").slice(1).map((r) => r.textContent);
    expect(rows).toEqual(["201611", "201823", "202414"]);
  });
  it("says so when there are no dated possible zombies", async () => {
    open(false, { ...POINTS, date: IDS.map(() => "") });
    expect(await screen.findByTestId("timelapse-empty")).toBeTruthy();
  });
});
