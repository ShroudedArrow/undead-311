import { describe, expect, it } from "vitest";
import { drawAtlas, iconFor, sprayPlan, spraySvg, iconMapping, OUTLINE_VARIANTS, rng, SPRITE_COUNT, SPRITE_OUTLINE_NAMES, SPRITE_SIZE, SPRITE_SOLID_NAMES, SPRITE_VARIANTS, variantFor } from "./sprites";
import { buildStyle, tilesUrl } from "./style";

describe("sprite atlas (REQ-WEB-MAP.1)", () => {
  it("offers 3 to 5 solid variants, plus outline variants, laid out without overlap", () => {
    expect(SPRITE_VARIANTS).toBeGreaterThanOrEqual(3);
    expect(SPRITE_VARIANTS).toBeLessThanOrEqual(5);
    const xs = Object.values(iconMapping()).map((d) => d.x);
    expect(new Set(xs).size).toBe(SPRITE_COUNT);
    expect(Math.max(...xs) + SPRITE_SIZE).toBe(SPRITE_SIZE * SPRITE_COUNT);
  });
  it("draws the headline tier solid and every other tier as an outline (REQ-WEB-TIER.1)", () => {
    expect(SPRITE_SOLID_NAMES as readonly string[]).toContain(iconFor("z1", "headline"));
    for (const tier of ["source_unknown", "sensitivity"]) {
      const names = new Set(Array.from({ length: 100 }, (_, i) => iconFor(`z${i}`, tier)));
      expect(names.size).toBe(OUTLINE_VARIANTS);
      for (const n of names) expect(SPRITE_OUTLINE_NAMES as readonly string[]).toContain(n);
    }
    for (const name of SPRITE_OUTLINE_NAMES) expect(iconMapping()[name]).toBeTruthy();
  });
  it("picks the same variant for the same id and uses every variant over many ids", () => {
    expect(variantFor("I-1:2")).toBe(variantFor("I-1:2"));
    const seen = new Set(Array.from({ length: 200 }, (_, i) => variantFor(`z${i}`)));
    expect(seen.size).toBe(SPRITE_VARIANTS);
  });
  it("draws deterministically with a seeded generator", () => {
    const run = () => {
      const calls: string[] = [];
      const ctx = {
        strokeStyle: "", fillStyle: "", lineWidth: 0, lineCap: "",
        beginPath: () => calls.push("b"), stroke: () => calls.push(`s${ctx.strokeStyle}${ctx.lineWidth}`), fill: () => calls.push("f"),
        clearRect: () => calls.push("c"), setLineDash: (d: number[]) => calls.push(`d${d.join("-")}`),
        arc: (...a: number[]) => calls.push(a.map((n) => n.toFixed(3)).join(",")),
      };
      return { n: drawAtlas(ctx as never), calls };
    };
    const a = run();
    expect(a.n).toBe(SPRITE_COUNT);
    expect(a.calls).toEqual(run().calls);
    expect(rng(1)()).toBe(rng(1)());
  });
});

describe("spray circle as an SVG for the share images (REQ-WEB-LINKS.2, UX-44)", () => {
  it("draws the same plan the atlas draws: the first sprite's ring arc matches sprayPlan", () => {
    const arcs: number[][] = [];
    const ctx = { strokeStyle: "", fillStyle: "", lineWidth: 0, lineCap: "", beginPath: () => undefined, stroke: () => undefined, fill: () => undefined, clearRect: () => undefined, setLineDash: () => undefined, arc: (...a: number[]) => arcs.push(a) };
    drawAtlas(ctx as never);
    const p = sprayPlan(0);
    expect(arcs[0]).toEqual([p.cx, p.cy, p.r, p.edge[0], p.edge[1]]);
    expect(arcs[1]).toEqual([p.cx, p.cy, p.r, p.ring[0], p.ring[1]]);
    expect(arcs).toHaveLength(SPRITE_VARIANTS * (2 + 46) + OUTLINE_VARIANTS * 2);
  });
  it("is a standalone pink ring with an Asphalt edge and speckle, deterministic per variant", () => {
    const svg = spraySvg(0, 64);
    expect(svg.startsWith("<svg ")).toBe(true);
    expect(svg).toContain("#ff3ea5");
    expect(svg.match(/<circle /g)).toHaveLength(46);
    expect(spraySvg(0)).toBe(spraySvg(0));
    expect(spraySvg(1)).not.toBe(spraySvg(0));
  });
});

describe("map style (REQ-WEB-MAP.1, REQ-WEB-DESIGN.1)", () => {
  const style = buildStyle(tilesUrl("http://localhost:4173", "/"), "attr");
  it("reads tiles from the same origin", () => {
    expect(JSON.stringify(style)).not.toMatch(/https?:\/\/(?!localhost)/);
    expect((style.sources.boston as { url: string }).url).toBe("pmtiles://http://localhost:4173/tiles/boston.pmtiles");
  });
  it("uses a light Concrete land, not a default dark theme", () => {
    const land = style.layers.find((l) => l.id === "land") as unknown as { paint: Record<string, string> };
    expect(land.paint["background-color"]).toBe("#cdcbc6");
  });
  it("only uses palette colors", () => {
    const hexes = JSON.stringify(style).match(/#[0-9a-f]{6}/gi) ?? [];
    for (const h of hexes) expect(["#cdcbc6", "#2e3134", "#f4f4ef", "#ff3ea5", "#f26b1d", "#efe08a"]).toContain(h.toLowerCase());
  });
});
