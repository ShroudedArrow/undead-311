import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { clearDataCache } from "../lib/data";
import { CardShare, CopyLink } from "./ShareLinks";

afterEach(() => { vi.unstubAllGlobals(); clearDataCache(); });

describe("Permalinks and share links (REQ-WEB-LINKS.1-2)", () => {
  it("copies the current address", async () => {
    const writeText = vi.fn(async () => undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    render(<CopyLink />);
    fireEvent.click(screen.getByRole("button", { name: "Copy link to this view" }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toBe("Link copied"));
    expect(writeText).toHaveBeenCalledWith(window.location.href);
  });
  it("shows the address when the clipboard is not available", async () => {
    vi.stubGlobal("navigator", {});
    render(<CopyLink />);
    fireEvent.click(screen.getByRole("button", { name: "Copy link to this view" }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain(window.location.href));
  });
  it("offers the share image only when the build rendered it", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, headers: new Headers({ "content-type": "text/html" }) }) as Response));
    const { unmount } = render(<CardShare zombieId="1:2" />);
    await waitFor(() => expect(fetch).toHaveBeenCalled());
    expect(screen.queryByRole("link", { name: "Download the share image" })).toBeNull();
    unmount();
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, headers: new Headers({ "content-type": "image/png" }) }) as Response));
    render(<CardShare zombieId="1:2" />);
    const a = await screen.findByRole("link", { name: "Download the share image" });
    expect(a.getAttribute("href")).toBe("/share/zombie/1-2.png");
  });
});

describe("Neighborhood permalink (REQ-WEB-LINKS.1)", () => {
  const INDEX = { data_version: "v", kind: "zombies", shards: [{ shard: "allston-brighton-2024", neighborhood: "Allston / Brighton", year: 2024, n: 1, districts: [] }] };
  const POINTS = { data_version: "v", n: 1, id: ["z1"], lat: [42.3], lon: [-71], tier: ["headline"], family: ["sign"], department: [null], neighborhood: ["Allston / Brighton"], year: [2024] };
  const open = (path: string) => {
    vi.stubGlobal("fetch", vi.fn(async (u: string) => ({ ok: true, status: 200, headers: new Headers(), json: async () => (String(u).endsWith("zombies/index.json") ? INDEX : String(u).endsWith("points.json") ? POINTS : { data_version: "v", last_run: "2026-11-11T00:00:00Z", ok: true, row_counts: {}, anomalies: [], segments: "missing" }) }) as Response));
    return render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>);
  };
  it("opens the map filtered to the neighborhood", async () => {
    open("/neighborhood/allston-brighton");
    expect(await screen.findByText(/\(1 selected\)/, undefined, { timeout: 8000 })).toBeTruthy();
  }, 12000);
  it("says so for an unknown neighborhood", async () => {
    open("/neighborhood/nowhere");
    expect(await screen.findByText(/No neighborhood called that/, undefined, { timeout: 8000 })).toBeTruthy();
  }, 12000);
});
