import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { clearDataCache } from "../lib/data";

vi.mock("../map/MapView", () => ({ default: () => <div data-testid="map" /> }));

const rec = (id: string) => ({ id, system: "legacy", open_time: "2026-01-10T15:00:00Z", close_time: "2026-01-12T15:00:00Z", type_raw: "Pothole", status: "Closed", closure_text: "done", street: "Main St", lat: 42.3, lon: -71.05 });
const IDS = ["z1", "z2", "z3"];
const POINTS = { data_version: "v", n: 3, id: IDS, lat: [42.3, 42.3, 42.3], lon: [-71, -71, -71], tier: ["headline", "headline", "headline"], family: ["sign", "sign", "sign"], department: [null, null, null], neighborhood: ["Dorchester", "Dorchester", "Dorchester"], year: [2026, 2026, 2026] };
const SHARD = { data_version: "v", shard: "dorchester-2026", cards: IDS.map((id, i) => ({ zombie_id: id, original: rec(`o${i}`), rereport: rec(`r${i}`), cause_of_death: "resolved", gap_days: 3 + i, resurrection_date: "2026-01-20", confidence: 0.8, tier: "headline", skeptic_verdict: "survives", skeptic_notes: `note ${i + 1}`, bulk_closure: false })) };
const STATUS = { data_version: "v", last_run: "2026-11-11T00:00:00Z", ok: true, row_counts: {}, anomalies: [], segments: "missing" };

const requested: string[] = [];

function setup(opts: { provisional?: boolean; reduced?: boolean; noFrozen?: boolean } = {}) {
  requested.length = 0;
  clearDataCache();
  vi.stubGlobal("matchMedia", (q: string) => ({ matches: !!opts.reduced && q.includes("reduce"), addEventListener() {}, removeEventListener() {}, media: q }));
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const u = String(url);
    requested.push(u);
    if (opts.noFrozen && u.includes("/frozen/")) return { ok: false, status: 404, json: async () => ({}) } as Response;
    const body = u.endsWith("judge_tour.json") ? { data_version: "v", provisional: opts.provisional ?? true, zombie_ids: IDS, source: "most_reports", params: { WINDOW_DAYS: 60, RADIUS_M: 30, matching: "segment" }, seed: null } : u.endsWith("points.json") ? POINTS : u.includes("cards/") ? SHARD : STATUS;
    return { ok: true, status: 200, json: async () => body } as Response;
  }));
  render(<MemoryRouter initialEntries={["/judge"]}><App /></MemoryRouter>);
}

beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); clearDataCache(); });

async function start() {
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
  const btn = await screen.findByRole("button", { name: "Start the tour" });
  await waitFor(() => expect((btn as HTMLButtonElement).disabled).toBe(false));
  await user.click(btn);
  return user;
}
const step = () => screen.getByTestId("tour-step").getAttribute("data-step");

describe("Judge mode (REQ-WEB-JUDGE.1, .3)", () => {
  it("plays three zombies in about 60 seconds and ends on the map link", async () => {
    setup();
    await start();
    expect(step()).toBe("0");
    expect(screen.getByText("Zombie 1 of 3")).toBeTruthy();
    expect(screen.getByText("note 1")).toBeTruthy();
    await act(async () => { vi.advanceTimersByTime(20500); });
    expect(step()).toBe("1");
    await act(async () => { vi.advanceTimersByTime(20000); });
    expect(step()).toBe("2");
    await act(async () => { vi.advanceTimersByTime(20000); });
    expect(screen.getByTestId("tour-done")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Open the map" })).toBeTruthy();
  });

  it("pauses and resumes", async () => {
    setup();
    const user = await start();
    await user.click(screen.getByRole("button", { name: "Pause" }));
    await act(async () => { vi.advanceTimersByTime(30000); });
    expect(step()).toBe("0");
    await user.click(screen.getByRole("button", { name: "Resume" }));
    await act(async () => { vi.advanceTimersByTime(21000); });
    expect(step()).toBe("1");
  });

  it("works from the keyboard: arrows move, space pauses, escape skips to the map", async () => {
    setup();
    const user = await start();
    await user.keyboard("{ArrowRight}");
    expect(step()).toBe("1");
    await user.keyboard("{ArrowLeft}");
    expect(step()).toBe("0");
    await user.keyboard(" ");
    expect(screen.getByRole("button", { name: "Resume" })).toBeTruthy();
    await user.keyboard("{Escape}");
    expect(await screen.findByTestId("map")).toBeTruthy();
  });

  it("skip button goes to the map", async () => {
    setup();
    const user = await start();
    await user.click(screen.getByRole("button", { name: "Skip the tour" }));
    expect(await screen.findByTestId("map")).toBeTruthy();
  });

  it("does not advance by itself under reduced motion, but the next button works", async () => {
    setup({ reduced: true });
    const user = await start();
    await act(async () => { vi.advanceTimersByTime(90000); });
    expect(step()).toBe("0");
    expect(screen.queryByRole("button", { name: "Pause" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Next zombie" }));
    expect(step()).toBe("1");
  });

  it("shows the provisional notice only while the tour is provisional (REQ-WEB-JUDGE.3)", async () => {
    setup({ provisional: true });
    expect(await screen.findByTestId("provisional-notice")).toBeTruthy();
  });
  it("shows no notice for a final tour", async () => {
    setup({ provisional: false });
    await screen.findByRole("button", { name: "Start the tour" });
    expect(screen.queryByTestId("provisional-notice")).toBeNull();
  });
});

describe("Judge mode reads the frozen snapshot (REQ-OPS-SNAP.2, ops#161)", () => {
  it("loads the tour, points and card shards from data/frozen/", async () => {
    setup();
    await screen.findByRole("button", { name: "Start the tour" });
    await waitFor(() => expect(requested.some((u) => u.includes("/data/frozen/cards/"))).toBe(true), { timeout: 4000 });
    expect(requested).toContain("/data/frozen/stats/judge_tour.json");
    expect(requested).toContain("/data/frozen/points.json");
    expect(requested.filter((u) => /\/data\/(stats\/judge_tour|points\.json|cards\/)/.test(u))).toEqual([]);
  });
  it("falls back to the live files when frozen/ is absent", async () => {
    setup({ noFrozen: true });
    await screen.findByRole("button", { name: "Start the tour" });
    await waitFor(() => expect(requested).toContain("/data/stats/judge_tour.json"));
    await waitFor(() => expect(requested.some((u) => u.startsWith("/data/cards/"))).toBe(true), { timeout: 4000 });
  });
});
