/**
 * Placeholder spray-circle sprite atlas for the zombie markers (REQ-WEB-MAP.1, design-system.md "Signature assets").
 * The final sprites are the owner's scanned and vectorized spray-paint circles; until they exist these are drawn
 * procedurally (a pink ring with spray speckle and an Asphalt edge so it meets 3:1 contrast on Concrete).
 * Drawing is deterministic: a seeded generator, no Math.random.
 */
import { PALETTE } from "./palette";

export const SPRITE_VARIANTS = 4;
export const SPRITE_SIZE = 64;
export const SPRITE_SOLID_NAMES = ["spray-0", "spray-1", "spray-2", "spray-3"] as const;
/** Outline-only markers for zombies outside the headline tier (REQ-WEB-TIER.1): a dashed hollow ring, so shape (not color) differs. */
export const OUTLINE_VARIANTS = 2;
export const SPRITE_OUTLINE_NAMES = ["outline-0", "outline-1"] as const;
export const SPRITE_COUNT = SPRITE_VARIANTS + OUTLINE_VARIANTS;

export interface IconDef {
  x: number;
  y: number;
  width: number;
  height: number;
  mask: boolean;
}

/** Atlas layout: one row, the solid sprites then the outline sprites, left to right. */
export function iconMapping(): Record<string, IconDef> {
  return Object.fromEntries(
    [...SPRITE_SOLID_NAMES, ...SPRITE_OUTLINE_NAMES].map((name, i) => [name, { x: i * SPRITE_SIZE, y: 0, width: SPRITE_SIZE, height: SPRITE_SIZE, mask: false }]),
  );
}

function hash(id: string): number {
  let h = 2166136261;
  for (let i = 0; i < id.length; i++) {
    h ^= id.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

/** Pick a solid sprite variant for a zombie id, stable across renders. */
export function variantFor(id: string): (typeof SPRITE_SOLID_NAMES)[number] {
  return SPRITE_SOLID_NAMES[hash(id) % SPRITE_VARIANTS];
}

/** The sprite for a zombie: solid for the headline tier, a dashed outline for any other tier (REQ-WEB-TIER.1). */
export function iconFor(id: string, tier: string): string {
  return tier === "headline" ? variantFor(id) : SPRITE_OUTLINE_NAMES[hash(id) % OUTLINE_VARIANTS];
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

type Ctx = Pick<CanvasRenderingContext2D, "beginPath" | "arc" | "stroke" | "fill" | "clearRect" | "setLineDash"> & {
  strokeStyle: unknown;
  fillStyle: unknown;
  lineWidth: number;
  lineCap: unknown;
};

/** Draw the atlas into a 2D context. Returns the number of sprites drawn. */
export function drawAtlas(ctx: Ctx): number {
  ctx.clearRect(0, 0, SPRITE_SIZE * SPRITE_COUNT, SPRITE_SIZE);
  for (let v = 0; v < SPRITE_VARIANTS; v++) {
    const rand = rng(1000 + v * 77);
    const cx = v * SPRITE_SIZE + SPRITE_SIZE / 2 + (rand() - 0.5) * 2;
    const cy = SPRITE_SIZE / 2 + (rand() - 0.5) * 2;
    const r = SPRITE_SIZE * 0.34 + rand() * 2;
    // Asphalt edge, then the pink ring on top: the ring reads on Concrete and on Asphalt.
    ctx.lineCap = "round";
    ctx.strokeStyle = PALETTE.asphalt;
    ctx.lineWidth = 11;
    ctx.beginPath();
    ctx.arc(cx, cy, r, rand() * 0.4, Math.PI * 2 - 0.15 - rand() * 0.3);
    ctx.stroke();
    ctx.strokeStyle = PALETTE.surveyPink;
    ctx.lineWidth = 7;
    ctx.beginPath();
    ctx.arc(cx, cy, r, rand() * 0.4, Math.PI * 2 - 0.15 - rand() * 0.3);
    ctx.stroke();
    // spray speckle around the ring
    for (let i = 0; i < 46; i++) {
      const ang = rand() * Math.PI * 2;
      const rad = r + (rand() - 0.5) * 15;
      ctx.fillStyle = PALETTE.surveyPink;
      ctx.beginPath();
      ctx.arc(cx + Math.cos(ang) * rad, cy + Math.sin(ang) * rad, 0.5 + rand() * 1.2, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  // Outline sprites: a thin dashed ring, hollow, Asphalt edge under a pink line.
  for (let v = 0; v < OUTLINE_VARIANTS; v++) {
    const rand = rng(5000 + v * 53);
    const cx = (SPRITE_VARIANTS + v) * SPRITE_SIZE + SPRITE_SIZE / 2;
    const cy = SPRITE_SIZE / 2;
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
    ctx.setLineDash([]);
  }
  return SPRITE_COUNT;
}

/** Build the atlas canvas in the browser. */
export function makeAtlasCanvas(): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = SPRITE_SIZE * SPRITE_COUNT;
  canvas.height = SPRITE_SIZE;
  const ctx = canvas.getContext("2d");
  if (ctx) drawAtlas(ctx);
  return canvas;
}
