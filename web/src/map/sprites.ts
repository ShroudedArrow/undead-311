/**
 * Spray-paint circle sprite atlas for the zombie markers (REQ-WEB-MAP.1, design-system.md "Signature assets").
 * Everything is drawn in code, from a seeded generator: no images, no Math.random. Each marker is a rough, uneven pink ring
 * (the radius wobbles, the stroke width changes along its length, and the end overshoots the start the way a sprayer's does)
 * with an Asphalt edge so it meets 3:1 contrast on Concrete, plus a stencil letter for the case-type family inside it.
 * Survey pink stays the only zombie colour: the letters are Asphalt. The final scanned circles may replace the ring later;
 * the letters and the atlas layout stay.
 *
 * Atlas layout: one column per family (plus one blank column for an unknown family); one row per ring variant, the solid
 * rows first and the dashed-outline rows after them.
 */
import { PALETTE } from "./palette.ts";

export const SPRITE_VARIANTS = 4;
export const SPRITE_SIZE = 64;
/** Outline-only markers for zombies outside the headline tier (REQ-WEB-TIER.1): a dashed hollow ring, so shape (not color) differs. */
export const OUTLINE_VARIANTS = 2;

/** Stencil letters per type family, as polylines in a unit box (x right, y down). Block letters: they must read at 10 px. */
export const FAMILY_GLYPHS = {
  pothole_roadway: { letter: "P", strokes: [[[0, 1], [0, 0], [0.8, 0], [1, 0.15], [1, 0.4], [0.8, 0.55], [0, 0.55]]] },
  sidewalk: { letter: "S", strokes: [[[1, 0.12], [0.85, 0], [0.15, 0], [0, 0.12], [0, 0.38], [0.15, 0.5], [0.85, 0.5], [1, 0.62], [1, 0.88], [0.85, 1], [0.15, 1], [0, 0.88]]] },
  streetlight: { letter: "L", strokes: [[[0, 0], [0, 1], [1, 1]]] },
  traffic_signal: { letter: "T", strokes: [[[0, 0], [1, 0]], [[0.5, 0], [0.5, 1]]] },
  sign: { letter: "X", strokes: [[[0, 0], [1, 1]], [[1, 0], [0, 1]]] },
  pavement_marking: { letter: "M", strokes: [[[0, 1], [0, 0], [0.5, 0.55], [1, 0], [1, 1]]] },
  street_fixture: { letter: "F", strokes: [[[1, 0], [0, 0], [0, 1]], [[0, 0.5], [0.75, 0.5]]] },
} as const satisfies Record<string, { letter: string; strokes: readonly (readonly (readonly [number, number])[])[] }>;

export type GlyphFamily = keyof typeof FAMILY_GLYPHS;
/** Legend and atlas order. */
export const FAMILY_ORDER = Object.keys(FAMILY_GLYPHS) as GlyphFamily[];
/** Column name for a family the atlas has no letter for: the ring is drawn with no letter. */
export const OTHER_FAMILY = "other";
const COLUMNS = FAMILY_ORDER.length + 1;
const ROWS = SPRITE_VARIANTS + OUTLINE_VARIANTS;
export const SPRITE_COUNT = COLUMNS * ROWS;
export const ATLAS_WIDTH = SPRITE_SIZE * COLUMNS;
export const ATLAS_HEIGHT = SPRITE_SIZE * ROWS;

const GLYPH_W = 13;
const GLYPH_H = 17;
const GLYPH_STROKE = 5;

export interface IconDef {
  x: number;
  y: number;
  width: number;
  height: number;
  mask: boolean;
}

const columnOf = (family: string): number => {
  const i = (FAMILY_ORDER as string[]).indexOf(family);
  return i < 0 ? FAMILY_ORDER.length : i;
};
const columnName = (col: number): string => FAMILY_ORDER[col] ?? OTHER_FAMILY;

/** Sprite names: `<family>-s<v>` solid (v 0 to 3), `<family>-o<v>` dashed outline (v 0 to 1); family is `other` when unknown. */
export function spriteName(family: string, solid: boolean, v: number): string {
  return `${columnName(columnOf(family))}-${solid ? "s" : "o"}${v}`;
}

/** Atlas layout for deck.gl's IconLayer. */
export function iconMapping(): Record<string, IconDef> {
  const out: Record<string, IconDef> = {};
  for (let c = 0; c < COLUMNS; c++) {
    for (let r = 0; r < ROWS; r++) {
      const solid = r < SPRITE_VARIANTS;
      const name = `${columnName(c)}-${solid ? "s" : "o"}${solid ? r : r - SPRITE_VARIANTS}`;
      out[name] = { x: c * SPRITE_SIZE, y: r * SPRITE_SIZE, width: SPRITE_SIZE, height: SPRITE_SIZE, mask: false };
    }
  }
  return out;
}

function hash(id: string): number {
  let h = 2166136261;
  for (let i = 0; i < id.length; i++) {
    h ^= id.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

/** Pick a solid ring variant (0 to 3) for a zombie id, stable across renders. Neighbours differ because ids differ. */
export function variantFor(id: string): number {
  return hash(id) % SPRITE_VARIANTS;
}

/** The sprite for a zombie: solid for the headline tier, a dashed outline for any other tier (REQ-WEB-TIER.1); the letter follows the family. */
export function iconFor(id: string, tier: string, family: string): string {
  return tier === "headline" ? spriteName(family, true, variantFor(id)) : spriteName(family, false, hash(id) % OUTLINE_VARIANTS);
}

/** Small deterministic generator (mulberry32). */
export function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

type Ctx = Pick<CanvasRenderingContext2D, "beginPath" | "arc" | "moveTo" | "lineTo" | "stroke" | "fill" | "clearRect" | "setLineDash"> & {
  strokeStyle: unknown;
  fillStyle: unknown;
  lineWidth: number;
  lineCap: unknown;
  lineJoin: unknown;
};

export interface SprayPoint {
  x: number;
  y: number;
  /** Width of the pink stroke up to the next point. */
  w: number;
}

export interface SprayPlan {
  cx: number;
  cy: number;
  r: number;
  /** The ring as a polyline. It runs a little more than once around, so the end overshoots the start. */
  points: SprayPoint[];
  dots: { x: number; y: number; r: number }[];
}

const EDGE_EXTRA = 4;

/** The geometry of ring variant `v` inside a SPRITE_SIZE square whose top-left corner is (ox, oy). The canvas atlas and the SVGs both draw this plan. */
export function sprayPlan(v: number, ox = 0, oy = 0): SprayPlan {
  const rand = rng(1000 + v * 77);
  const cx = ox + SPRITE_SIZE / 2 + (rand() - 0.5) * 2;
  const cy = oy + SPRITE_SIZE / 2 + (rand() - 0.5) * 2;
  const r = SPRITE_SIZE * 0.34 + rand() * 2;
  const start = rand() * Math.PI * 2;
  const overshoot = 0.35 + rand() * 0.4;
  const span = Math.PI * 2 + overshoot;
  const squash = 1 + (rand() - 0.5) * 0.08;
  const p1 = rand() * 6.28;
  const p2 = rand() * 6.28;
  const n = 40;
  const points: SprayPoint[] = [];
  for (let i = 0; i <= n; i++) {
    const a = start + (span * i) / n;
    const drift = Math.max(0, a - start - Math.PI * 2) * 3; // the overshoot lands a little outside the first pass
    const rad = r + Math.sin(a * 2 + p1) * 0.9 + Math.sin(a * 3 + p2) * 0.6 + (rand() - 0.5) * 0.6 + drift;
    // thick where the can lingers, thin where it moves: 5.5 to 8.5 px
    const w = 7 + Math.sin(a * 1.5 + p2) * 1 + (rand() - 0.5) * 1;
    points.push({ x: cx + Math.cos(a) * rad * squash, y: cy + Math.sin(a) * rad, w });
  }
  const dots = [];
  for (let i = 0; i < 46; i++) {
    const ang = rand() * Math.PI * 2;
    const rad = r + (rand() - 0.5) * 15;
    dots.push({ x: cx + Math.cos(ang) * rad, y: cy + Math.sin(ang) * rad, r: 0.5 + rand() * 1.2 });
  }
  return { cx, cy, r, points, dots };
}

/** The family's stencil strokes placed with the box centred on (cx, cy), in sprite pixels. */
export function glyphStrokes(family: string, cx: number, cy: number): [number, number][][] {
  const g = (FAMILY_GLYPHS as Record<string, { strokes: readonly (readonly (readonly [number, number])[])[] }>)[family];
  if (!g) return [];
  return g.strokes.map((s) => s.map(([u, w]) => [cx + (u - 0.5) * GLYPH_W, cy + (w - 0.5) * GLYPH_H] as [number, number]));
}

const f2 = (n: number): string => n.toFixed(2);

function glyphSvgInner(family: string, cx: number, cy: number): string {
  const strokes = glyphStrokes(family, cx, cy);
  if (strokes.length === 0) return "";
  const d = strokes.map((s) => "M" + s.map(([x, y]) => `${f2(x)} ${f2(y)}`).join("L")).join("");
  return `<path d="${d}" fill="none" stroke="${PALETTE.asphalt}" stroke-width="${GLYPH_STROKE}" stroke-linejoin="miter" stroke-linecap="butt"/>`;
}

/** One solid spray-circle as a standalone SVG string: the same ring, edge and speckle as the map marker, with the family's letter when given. Used by the share images (REQ-WEB-LINKS.2) and the legend. */
export function spraySvg(v = 0, px = SPRITE_SIZE, family?: string): string {
  const p = sprayPlan(v);
  const seg = (a: SprayPoint, b: SprayPoint, color: string, width: number) =>
    `<path d="M${f2(a.x)} ${f2(a.y)}L${f2(b.x)} ${f2(b.y)}" stroke="${color}" stroke-width="${f2(width)}"/>`;
  const pairs = p.points.slice(0, -1).map((a, i) => [a, p.points[i + 1]] as const);
  const edge = pairs.map(([a, b]) => seg(a, b, PALETTE.asphalt, (a.w + b.w) / 2 + EDGE_EXTRA)).join("");
  const ring = pairs.map(([a, b]) => seg(a, b, PALETTE.surveyPink, (a.w + b.w) / 2)).join("");
  const dots = p.dots.map((d) => `<circle cx="${f2(d.x)}" cy="${f2(d.y)}" r="${f2(d.r)}"/>`).join("");
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" width="${px}" height="${px}" viewBox="0 0 ${SPRITE_SIZE} ${SPRITE_SIZE}" aria-hidden="true" focusable="false">` +
    `<g fill="none" stroke-linecap="round">${edge}${ring}</g>` +
    `<g fill="${PALETTE.surveyPink}">${dots}</g>` +
    (family ? glyphSvgInner(family, p.cx, p.cy) : "") +
    `</svg>`
  );
}

function strokeRing(ctx: Ctx, plan: SprayPlan): void {
  const pairs = plan.points.slice(0, -1).map((a, i) => [a, plan.points[i + 1]] as const);
  ctx.lineCap = "round";
  // Asphalt edge first, then the pink ring on top: the ring reads on Concrete and on Asphalt.
  for (const [color, extra] of [[PALETTE.asphalt, EDGE_EXTRA], [PALETTE.surveyPink, 0]] as const) {
    ctx.strokeStyle = color;
    for (const [a, b] of pairs) {
      ctx.lineWidth = (a.w + b.w) / 2 + extra;
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
    }
  }
  ctx.fillStyle = PALETTE.surveyPink;
  for (const d of plan.dots) {
    ctx.beginPath();
    ctx.arc(d.x, d.y, d.r, 0, Math.PI * 2);
    ctx.fill();
  }
}

function strokeGlyph(ctx: Ctx, family: string, cx: number, cy: number): void {
  ctx.setLineDash([]);
  ctx.strokeStyle = PALETTE.asphalt;
  ctx.lineWidth = GLYPH_STROKE;
  ctx.lineCap = "butt";
  ctx.lineJoin = "miter";
  for (const s of glyphStrokes(family, cx, cy)) {
    ctx.beginPath();
    s.forEach(([x, y], i) => (i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)));
    ctx.stroke();
  }
}

/** Draw the atlas into a 2D context. Returns the number of sprites drawn. */
export function drawAtlas(ctx: Ctx): number {
  ctx.clearRect(0, 0, ATLAS_WIDTH, ATLAS_HEIGHT);
  for (let c = 0; c < COLUMNS; c++) {
    const family = columnName(c);
    for (let v = 0; v < SPRITE_VARIANTS; v++) {
      const plan = sprayPlan(v, c * SPRITE_SIZE, v * SPRITE_SIZE);
      strokeRing(ctx, plan);
      strokeGlyph(ctx, family, plan.cx, plan.cy);
    }
    // Outline sprites: a thin dashed ring, hollow, Asphalt edge under a pink line.
    for (let v = 0; v < OUTLINE_VARIANTS; v++) {
      const rand = rng(5000 + v * 53);
      const cx = c * SPRITE_SIZE + SPRITE_SIZE / 2;
      const cy = (SPRITE_VARIANTS + v) * SPRITE_SIZE + SPRITE_SIZE / 2;
      const r = SPRITE_SIZE * 0.32 + rand() * 2;
      ctx.lineCap = "butt";
      ctx.setLineDash([7, 5]);
      ctx.strokeStyle = PALETTE.asphalt;
      ctx.lineWidth = 6;
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.stroke();
      ctx.strokeStyle = PALETTE.surveyPink;
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.stroke();
      strokeGlyph(ctx, family, cx, cy);
    }
  }
  return SPRITE_COUNT;
}

/** Build the atlas canvas in the browser. */
export function makeAtlasCanvas(): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = ATLAS_WIDTH;
  canvas.height = ATLAS_HEIGHT;
  const ctx = canvas.getContext("2d");
  if (ctx) drawAtlas(ctx);
  return canvas;
}
