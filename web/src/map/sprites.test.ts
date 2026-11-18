import { describe, expect, it } from "vitest";
import {
  ATLAS_HEIGHT, ATLAS_WIDTH, CLUSTER_VARIANTS, clusterIcon, clusterPlan, clusterSvg, drawAtlas, FAMILY_GLYPHS, FAMILY_ORDER, glyphStrokes, iconFor, iconMapping, OTHER_FAMILY, OUTLINE_VARIANTS, rng, SPRITE_COUNT, SPRITE_SIZE,
  SPRITE_VARIANTS, sprayPlan, spraySvg, spriteName, variantFor,
} from "./sprites";
import { buildStyle, tilesUrl } from "./style";

function mockCtx() {
  const calls: string[] = [];
  const ctx = {
    strokeStyle: "" as unknown, fillStyle: "" as unknown, lineWidth: 0, lineCap: "" as unknown, lineJoin: "" as unknown,
    beginPath: () => calls.push("b"), stroke: () => calls.push(`s${String(ctx.strokeStyle)}${ctx.lineWidth.toFixed(2)}`), fill: () => calls.push("f"),
    clearRect: () => calls.push("c"), setLineDash: (d: number[]) => calls.push(`d${d.join("-")}`),
    moveTo: (x: number, y: number) => calls.push(`m${x.toFixed(3)},${y.toFixed(3)}`), lineTo: (x: number, y: number) => calls.push(`l${x.toFixed(3)},${y.toFixed(3)}`),
    arc: (...a: number[]) => calls.push(a.map((n) => n.toFixed(3)).join(",")),
  };
  return { ctx, calls };
}

describe("sprite atlas (REQ-WEB-MAP.1)", () => {
  it("offers 3 to 5 ring variants, plus outline variants, laid out on a grid without overlap", () => {
    expect(SPRITE_VARIANTS).toBeGreaterThanOrEqual(3);
    expect(SPRITE_VARIANTS).toBeLessThanOrEqual(5);
    const cells = Object.values(iconMapping()).map((d) => `${d.x},${d.y}`);
    expect(cells).toHaveLength(SPRITE_COUNT);
    expect(new Set(cells).size).toBe(SPRITE_COUNT);
    for (const d of Object.values(iconMapping())) {
      expect(d.x + d.width).toBeLessThanOrEqual(ATLAS_WIDTH);
      expect(d.y + d.height).toBeLessThanOrEqual(ATLAS_HEIGHT);
      expect(d.width).toBe(SPRITE_SIZE);
    }
  });
  it("has one stencil letter for each of the seven type families, all different", () => {
    expect(FAMILY_ORDER).toEqual(["pothole_roadway", "sidewalk", "streetlight", "traffic_signal", "sign", "pavement_marking", "street_fixture"]);
    expect(FAMILY_ORDER.map((f) => FAMILY_GLYPHS[f].letter).join("")).toBe("PSLTXMF");
    const shapes = new Set(FAMILY_ORDER.map((f) => JSON.stringify(FAMILY_GLYPHS[f].strokes)));
    expect(shapes.size).toBe(FAMILY_ORDER.length);
  });
  it("keeps every letter inside its box, so it fits inside the ring", () => {
    for (const f of FAMILY_ORDER) for (const s of FAMILY_GLYPHS[f].strokes) for (const [u, v] of s) {
      expect(u).toBeGreaterThanOrEqual(0); expect(u).toBeLessThanOrEqual(1);
      expect(v).toBeGreaterThanOrEqual(0); expect(v).toBeLessThanOrEqual(1);
    }
    const plan = sprayPlan(0);
    for (const f of FAMILY_ORDER) for (const s of glyphStrokes(f, plan.cx, plan.cy)) for (const [x, y] of s) {
      expect(Math.hypot(x - plan.cx, y - plan.cy)).toBeLessThan(plan.r - 7); // inside the inner edge of the ring
    }
    expect(glyphStrokes("no_such_family", 0, 0)).toEqual([]);
  });
  it("draws the headline tier solid and every other tier as an outline, in the family's column (REQ-WEB-TIER.1)", () => {
    const mapping = iconMapping();
    for (const family of [...FAMILY_ORDER, "unlisted"]) {
      const solid = iconFor("z1", "headline", family);
      expect(solid).toMatch(/-s[0-3]$/);
      expect(mapping[solid]).toBeTruthy();
      for (const tier of ["source_unknown", "sensitivity", "city_rereport"]) {
        const names = new Set(Array.from({ length: 100 }, (_, i) => iconFor(`z${i}`, tier, family)));
        expect(names.size).toBe(OUTLINE_VARIANTS);
        for (const n of names) { expect(n).toMatch(/-o[01]$/); expect(mapping[n]).toBeTruthy(); }
      }
    }
    expect(spriteName("unlisted", true, 2)).toBe(`${OTHER_FAMILY}-s2`);
  });
  it("picks the same variant for the same id and uses every variant over many ids", () => {
    expect(variantFor("I-1:2")).toBe(variantFor("I-1:2"));
    const seen = new Set(Array.from({ length: 200 }, (_, i) => variantFor(`z${i}`)));
    expect(seen.size).toBe(SPRITE_VARIANTS);
  });
  it("draws deterministically with a seeded generator", () => {
    const run = () => { const m = mockCtx(); return { n: drawAtlas(m.ctx as never), calls: m.calls }; };
    const a = run();
    expect(a.n).toBe(SPRITE_COUNT);
    expect(a.calls).toEqual(run().calls);
    expect(rng(1)()).toBe(rng(1)());
  });
  it("paints only Asphalt and Survey pink, so pink stays the only zombie colour", () => {
    const m = mockCtx();
    drawAtlas(m.ctx as never);
    const colors = new Set(m.calls.filter((c) => c.startsWith("s#")).map((c) => c.slice(1, 8)));
    expect([...colors].sort()).toEqual(["#2e3134", "#ff3ea5"]);
  });
});

describe("spray-dot clusters for the density view (REQ-WEB-MAP.1)", () => {
  it("has cluster sprites in the atlas, in their own row, inside the atlas", () => {
    const m = iconMapping();
    for (let v = 0; v < CLUSTER_VARIANTS; v++) {
      const d = m[`cluster-${v}`];
      expect(d).toBeTruthy();
      expect(d.y + d.height).toBeLessThanOrEqual(ATLAS_HEIGHT);
    }
    expect(m[clusterIcon("3:5@11")]).toBeTruthy();
    expect(clusterIcon("3:5@11")).toBe(clusterIcon("3:5@11"));
  });
  it("is a cloud of dots inside its cell, thicker in the middle, and different for each variant", () => {
    for (let v = 0; v < CLUSTER_VARIANTS; v++) {
      const dots = clusterPlan(v, 64, 128);
      expect(dots.length).toBeGreaterThan(40);
      for (const d of dots) {
        expect(d.x - d.r).toBeGreaterThan(64);
        expect(d.x + d.r).toBeLessThan(128);
        expect(d.y - d.r).toBeGreaterThan(128);
        expect(d.y + d.r).toBeLessThan(192);
      }
      const inner = dots.filter((d) => Math.hypot(d.x - 96, d.y - 160) < 12).length;
      expect(inner / dots.length).toBeGreaterThan(0.25); // a uniform cloud would put about 27% there; the centre is denser
    }
    expect(JSON.stringify(clusterPlan(0))).not.toBe(JSON.stringify(clusterPlan(1)));
  });
  it("draws as pink dots with an Asphalt edge, for the legend too", () => {
    const svg = clusterSvg(0, 28);
    expect(svg).toContain("#ff3ea5");
    expect(svg).toContain("#2e3134");
    expect(svg.match(/<circle /g)).toHaveLength(clusterPlan(0).length * 2);
  });
});

describe("rough ring (REQ-WEB-MAP.1, design-system.md signature assets)", () => {
  it("makes the four ring variants different from each other, so neighbours do not look identical", () => {
    const rings = Array.from({ length: SPRITE_VARIANTS }, (_, v) => JSON.stringify(sprayPlan(v).points.map((p) => [p.x.toFixed(2), p.y.toFixed(2)])));
    expect(new Set(rings).size).toBe(SPRITE_VARIANTS);
  });
  it("is uneven: the radius wobbles, the width changes along the stroke, and the end overshoots the start", () => {
    for (let v = 0; v < SPRITE_VARIANTS; v++) {
      const p = sprayPlan(v);
      const radii = p.points.map((q) => Math.hypot(q.x - p.cx, q.y - p.cy));
      expect(Math.max(...radii) - Math.min(...radii)).toBeGreaterThan(1.5);
      const widths = p.points.map((q) => q.w);
      expect(Math.max(...widths) - Math.min(...widths)).toBeGreaterThan(0.8);
      const first = p.points[0];
      const last = p.points[p.points.length - 1];
      expect(Math.hypot(first.x - last.x, first.y - last.y)).toBeGreaterThan(0.5); // does not close exactly
    }
  });
  it("keeps a variant inside its cell wherever the cell sits in the atlas", () => {
    const p = sprayPlan(2, 128, 192);
    for (const q of [...p.points, ...p.dots]) {
      expect(q.x).toBeGreaterThanOrEqual(128); expect(q.x).toBeLessThanOrEqual(128 + SPRITE_SIZE);
      expect(q.y).toBeGreaterThanOrEqual(192); expect(q.y).toBeLessThanOrEqual(192 + SPRITE_SIZE);
    }
  });
});

describe("spray circle as an SVG for the share images and the legend (REQ-WEB-LINKS.2, UX-44)", () => {
  it("draws the same plan the atlas draws: the first stroke of the first cell starts at sprayPlan's first point", () => {
    const m = mockCtx();
    drawAtlas(m.ctx as never);
    const p = sprayPlan(0);
    expect(m.calls[2]).toBe(`m${p.points[0].x.toFixed(3)},${p.points[0].y.toFixed(3)}`);
  });
  it("is a standalone pink ring with an Asphalt edge and speckle, deterministic per variant", () => {
    const svg = spraySvg(0, 64);
    expect(svg.startsWith("<svg ")).toBe(true);
    expect(svg).toContain("#ff3ea5");
    expect(svg).toContain("#2e3134");
    expect(svg.match(/<circle /g)).toHaveLength(46);
    expect(spraySvg(0)).toBe(spraySvg(0));
    expect(spraySvg(1)).not.toBe(spraySvg(0));
  });
  it("adds the family's letter only when asked", () => {
    expect(spraySvg(0, 64)).not.toContain("stroke-linejoin");
    expect(spraySvg(0, 64, "sidewalk")).toContain("stroke-linejoin");
    expect(spraySvg(0, 64, "sidewalk")).not.toBe(spraySvg(0, 64, "streetlight"));
    expect(spraySvg(0, 64, "unlisted")).toBe(spraySvg(0, 64));
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
