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

export interface IconDef {
  x: number;
  y: number;
  width: number;
  height: number;
  mask: boolean;
}

/** Atlas layout: one row, SPRITE_VARIANTS sprites left to right. */
export function iconMapping(): Record<string, IconDef> {
  return Object.fromEntries(
    SPRITE_SOLID_NAMES.map((name, i) => [name, { x: i * SPRITE_SIZE, y: 0, width: SPRITE_SIZE, height: SPRITE_SIZE, mask: false }]),
  );
}

/** Pick a sprite variant for a zombie id, stable across renders. */
export function variantFor(id: string): (typeof SPRITE_SOLID_NAMES)[number] {
  let h = 2166136261;
  for (let i = 0; i < id.length; i++) {
    h ^= id.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return SPRITE_SOLID_NAMES[(h >>> 0) % SPRITE_VARIANTS];
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

type Ctx = Pick<CanvasRenderingContext2D, "beginPath" | "arc" | "stroke" | "fill" | "clearRect"> & {
  strokeStyle: unknown;
  fillStyle: unknown;
  lineWidth: number;
  lineCap: unknown;
};

/** Draw the atlas into a 2D context. Returns the number of sprites drawn. */
export function drawAtlas(ctx: Ctx): number {
  ctx.clearRect(0, 0, SPRITE_SIZE * SPRITE_VARIANTS, SPRITE_SIZE);
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
  return SPRITE_VARIANTS;
}

/** Build the atlas canvas in the browser. */
export function makeAtlasCanvas(): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = SPRITE_SIZE * SPRITE_VARIANTS;
  canvas.height = SPRITE_SIZE;
  const ctx = canvas.getContext("2d");
  if (ctx) drawAtlas(ctx);
  return canvas;
}
