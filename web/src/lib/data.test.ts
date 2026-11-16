import { afterEach, describe, expect, it, vi } from "vitest";
import { clearDataCache, dataUrl, loadData, loadFrozen, loadFrozenOnce, loadOnce } from "./data";
import { STATS_FILES, statsPath } from "./statsFiles";
import { parseStatus } from "./parse";

const GOOD = { data_version: "v", last_run: "2026-11-11T02:00:00Z", ok: true, row_counts: {}, anomalies: [], segments: "missing" };

function mockFetch(body: unknown, ok = true, status = 200) {
  const fn = vi.fn(async () => ({ ok, status, json: async () => body }) as Response);
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => {
  vi.unstubAllGlobals();
  clearDataCache();
});

describe("loadData (REQ-WEB-DATA.1-2)", () => {
  it("parses a valid file", async () => {
    mockFetch(GOOD);
    const r = await loadData("status.json", parseStatus);
    expect(r.status).toBe("ok");
  });
  it("returns an error state for a file that fails its schema, naming the file", async () => {
    mockFetch({ data_version: "v" });
    const r = await loadData("status.json", parseStatus);
    expect(r).toMatchObject({ status: "error", file: "status.json" });
  });
  it("returns an error state for HTTP failure and network failure", async () => {
    mockFetch({}, false, 404);
    expect(await loadData("x.json", parseStatus)).toMatchObject({ status: "error", error: "HTTP 404" });
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("offline"); }));
    expect(await loadData("x.json", parseStatus)).toMatchObject({ status: "error", error: "offline" });
  });
  it("only requests same-origin relative URLs (REQ-WEB-PERF.2)", async () => {
    const fn = mockFetch(GOOD);
    await loadOnce("status.json", parseStatus);
    await loadOnce("status.json", parseStatus);
    expect(fn).toHaveBeenCalledTimes(1);
    const url = String((fn.mock.calls[0] as unknown[])[0]);
    expect(url.startsWith("/")).toBe(true);
    expect(url).not.toMatch(/^https?:/);
  });
});

describe("stats files load from data/stats/ (REQ-WEB-DATA.1, ops#101)", () => {
  it("maps every statistics file under stats/ and leaves the other files flat", () => {
    for (const f of STATS_FILES) expect(dataUrl(f)).toMatch(/\/data\/stats\/[a-z_]+\.json$/);
    for (const f of ["status.json", "points.json", "points/city_rereport.json", "zombies/index.json", "zombies/a-2020.json", "exclusions.json", "bulk_closures.json", "cards/a-2020.json"]) {
      expect(dataUrl(f)).toMatch(/\/data\/(?!stats\/)/);
      expect(statsPath(f)).toBe(f);
    }
  });
  it("requests scorecard.json at /data/stats/scorecard.json", async () => {
    const fn = mockFetch(GOOD);
    await loadData("scorecard.json", parseStatus);
    expect(String((fn.mock.calls[0] as unknown[])[0])).toBe("/data/stats/scorecard.json");
  });
});

describe("frozen judging snapshot (REQ-OPS-SNAP.2, ops#161)", () => {
  it("reads data/frozen/<path> first", async () => {
    const fn = mockFetch(GOOD);
    const r = await loadFrozenOnce("status.json", parseStatus);
    expect(r.status).toBe("ok");
    expect(String((fn.mock.calls[0] as unknown[])[0])).toBe("/data/frozen/status.json");
    expect(fn).toHaveBeenCalledTimes(1);
  });
  it("keeps the stats/ folder inside frozen/", async () => {
    const fn = mockFetch(GOOD);
    await loadFrozen("judge_tour.json", parseStatus);
    expect(String((fn.mock.calls[0] as unknown[])[0])).toBe("/data/frozen/stats/judge_tour.json");
  });
  it("falls back to the live file when frozen/ is absent (HTTP 404, app shell or network error)", async () => {
    const urls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (u: string) => {
      urls.push(u);
      return u.includes("/frozen/") ? ({ ok: false, status: 404, json: async () => ({}) } as Response) : ({ ok: true, status: 200, json: async () => GOOD } as Response);
    }));
    expect((await loadFrozen("status.json", parseStatus)).status).toBe("ok");
    expect(urls).toEqual(["/data/frozen/status.json", "/data/status.json"]);
    vi.stubGlobal("fetch", vi.fn(async (u: string) => {
      if (u.includes("/frozen/")) return { ok: true, status: 200, json: async () => { throw new SyntaxError("<!doctype"); } } as unknown as Response;
      return { ok: true, status: 200, json: async () => GOOD } as Response;
    }));
    expect((await loadFrozen("status.json", parseStatus)).status).toBe("ok");
  });
  it("does not switch silently to live data when a frozen file fails its schema", async () => {
    const fn = mockFetch({ data_version: "v" });
    const r = await loadFrozen("status.json", parseStatus);
    expect(r).toMatchObject({ status: "error", file: "frozen/status.json" });
    expect(fn).toHaveBeenCalledTimes(1);
  });
});
