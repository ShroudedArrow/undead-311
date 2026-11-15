import { fireEvent, render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { clearDataCache } from "../lib/data";
import { Sliders } from "./Sliders";

const GRID = readFileSync(join(__dirname, "..", "..", "public", "data", "stats", "sensitivity_grid.json"), "utf8");
afterEach(() => { vi.unstubAllGlobals(); clearDataCache(); });
const serve = (body: string, ok = true) => vi.stubGlobal("fetch", vi.fn(async () => ({ ok, status: ok ? 200 : 500, json: async () => JSON.parse(body) }) as Response));

describe("Sensitivity sliders (REQ-WEB-SLIDERS.1)", () => {
  it("starts on the headline run and switches instantly between grid points", async () => {
    serve(GRID);
    render(<Sliders />);
    expect((await screen.findByTestId("slider-headline")).textContent).toBe("1009");
    expect(screen.getByText("This is the setting used for the headline.")).toBeTruthy();
    fireEvent.change(screen.getByRole("slider", { name: /Days to re-report/ }), { target: { value: "0" } });
    expect(screen.getByTestId("window-value").textContent).toBe("30");
    expect(screen.getByTestId("slider-headline").textContent).toBe("698");
    expect(screen.getByText(/The headline uses same street segment matching, 30 m and 60 days/)).toBeTruthy();
  });
  it("matching radio and distance slider pick the matching grid point; every value is written out", async () => {
    serve(GRID);
    render(<Sliders />);
    await screen.findByTestId("slider-headline");
    fireEvent.click(screen.getByLabelText("Distance only"));
    fireEvent.change(screen.getByRole("slider", { name: /Distance/ }), { target: { value: "0" } });
    expect(screen.getByTestId("radius-value").textContent).toBe("15");
    const g = JSON.parse(GRID).points.find((p: { matching: string; radius_m: number; window_days: number }) => p.matching === "radius" && p.radius_m === 15 && p.window_days === 60);
    expect(screen.getByTestId("slider-headline").textContent).toBe(String(g.headline));
  });
  it("notes that distance matters little for segment matching, and shows the run without Street Light Other", async () => {
    serve(GRID);
    render(<Sliders />);
    await screen.findByTestId("slider-headline");
    expect(screen.getByText(/only applies to cases that could not be placed on a segment/)).toBeTruthy();
    expect(screen.getByTestId("slider-slo").textContent).toContain("1000 headline possible zombies and 3037 in all tiers");
    fireEvent.click(screen.getByLabelText("Distance only"));
    expect(screen.queryByText(/only applies to cases that could not be placed/)).toBeNull();
  });
  it("says so when a setting is not in the grid, and shows an error state for a bad file", async () => {
    const g = JSON.parse(GRID);
    g.points = g.points.filter((p: { matching: string; radius_m: number; window_days: number }) => !(p.matching === "radius" && p.radius_m === 50 && p.window_days === 90));
    serve(JSON.stringify(g));
    const { unmount } = render(<Sliders />);
    await screen.findByTestId("slider-headline");
    fireEvent.click(screen.getByLabelText("Distance only"));
    fireEvent.change(screen.getByRole("slider", { name: /Distance/ }), { target: { value: "2" } });
    fireEvent.change(screen.getByRole("slider", { name: /Days to re-report/ }), { target: { value: "2" } });
    expect(screen.getByTestId("slider-no-point")).toBeTruthy();
    unmount();
    clearDataCache();
    serve(JSON.stringify({ data_version: "v" }));
    render(<Sliders />);
    expect(await screen.findByText(/sensitivity_grid.json/)).toBeTruthy();
  });
});
