import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { clearDataCache, loadOnce, useData } from "./data";

const ok = (d: unknown) => ({ ok: true as const, data: d });
afterEach(() => { vi.unstubAllGlobals(); clearDataCache(); });

function Probe({ file }: { file: string }) {
  const s = useData(file, ok);
  return <p data-testid="s">{s.status}</p>;
}

describe("data cache: a later reader starts with the data (layout shift)", () => {
  it("renders a component that mounts after the file came back with the data on its first render, not with a loading state", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ a: 1 }) }) as Response));
    await loadOnce("x.json", ok);
    const seen: string[] = [];
    function First() {
      const s = useData("x.json", ok);
      seen.push(s.status);
      return null;
    }
    render(<First />);
    expect(seen[0]).toBe("ok");
  });
  it("still loads once and shows loading first for a file nobody asked for yet", async () => {
    const fetch = vi.fn(async () => ({ ok: true, status: 200, json: async () => ({}) }) as Response);
    vi.stubGlobal("fetch", fetch);
    render(<Probe file="y.json" />);
    expect(screen.getByTestId("s").textContent).toBe("loading");
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    expect(await screen.findByText("ok")).toBeTruthy();
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it("forgets results when the cache is cleared, even for a load that finishes afterwards", async () => {
    let release: (r: Response) => void = () => undefined;
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((r) => { release = r; })));
    const p = loadOnce("z.json", ok);
    clearDataCache();
    release({ ok: true, status: 200, json: async () => ({}) } as Response);
    await p;
    const seen: string[] = [];
    function Read() { seen.push(useData("z.json", ok).status); return null; }
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => undefined)));
    render(<Read />);
    expect(seen[0]).toBe("loading");
  });
  it("does not start a load of its own when it mounts with a result in hand, so nothing loads after the cache is cleared", async () => {
    const fetch = vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ a: 1 }) }) as Response);
    vi.stubGlobal("fetch", fetch);
    await loadOnce("w.json", ok);
    expect(fetch).toHaveBeenCalledTimes(1);
    const { rerender } = render(<Probe file="w.json" />);
    expect(screen.getByTestId("s").textContent).toBe("ok");
    clearDataCache();
    rerender(<Probe file="w.json" />);
    await act(async () => { await Promise.resolve(); });
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("s").textContent).toBe("ok");
  });
  it("loads the new file when the file name changes", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => ({}) }) as Response));
    await loadOnce("p.json", ok);
    const { rerender } = render(<Probe file="p.json" />);
    expect(screen.getByTestId("s").textContent).toBe("ok");
    rerender(<Probe file="q.json" />);
    expect(screen.getByTestId("s").textContent).toBe("loading");
    expect(await screen.findByText("ok")).toBeTruthy();
  });
});
