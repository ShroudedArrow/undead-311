// REQ-OPS-CAPTURE.1: a small GIF89a writer, so the time-lapse GIF needs no extra dependency (no ffmpeg, no Pillow).
// Colours are mapped to a fixed 256-colour palette (6 x 7 x 6 levels); there is no dithering.
//
// Usage as a module: encodeGif([{ width, height, rgba: Uint8Array }], { delaysMs: [..] }) -> Buffer
// Usage as a CLI (used by the tests): node gif.mjs <out.gif> <width> <height> <frames> <delayMs>   (writes a test pattern)
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const CLEAR = 256;
const EOI = 257;

/** Index into the fixed palette: 6 red levels x 7 green levels x 6 blue levels (252 colours; greys map to greys). */
export function paletteIndex(r, g, b) {
  return Math.round((r * 5) / 255) * 42 + Math.round((g * 6) / 255) * 6 + Math.round((b * 5) / 255);
}

function palette() {
  const out = Buffer.alloc(768); // entries 252 to 255 stay black and are never used
  for (let r = 0; r < 6; r++) {
    for (let g = 0; g < 7; g++) {
      for (let b = 0; b < 6; b++) {
        const i = r * 42 + g * 6 + b;
        out[i * 3] = Math.round((r * 255) / 5);
        out[i * 3 + 1] = Math.round((g * 255) / 6);
        out[i * 3 + 2] = Math.round((b * 255) / 5);
      }
    }
  }
  return out;
}

/** GIF variable-code-size LZW with 8-bit pixels. Returns the packed bytes. */
export function lzw(pixels) {
  const out = [];
  let cur = 0;
  let bits = 0;
  const emit = (code, size) => {
    cur |= code << bits;
    bits += size;
    while (bits >= 8) {
      out.push(cur & 255);
      cur >>>= 8;
      bits -= 8;
    }
  };
  let size = 9;
  let next = 258;
  let dict = new Map();
  emit(CLEAR, size);
  let prefix = pixels[0];
  for (let i = 1; i < pixels.length; i++) {
    const c = pixels[i];
    const key = prefix * 256 + c;
    const hit = dict.get(key);
    if (hit !== undefined) {
      prefix = hit;
      continue;
    }
    emit(prefix, size);
    if (next === 4096) {
      emit(CLEAR, size);
      dict = new Map();
      size = 9;
      next = 258;
    } else {
      if (next >= 1 << size) size++;
      dict.set(key, next++);
    }
    prefix = c;
  }
  emit(prefix, size);
  emit(EOI, size);
  if (bits > 0) out.push(cur & 255);
  return Buffer.from(out);
}

function subBlocks(data) {
  const parts = [];
  for (let i = 0; i < data.length; i += 255) {
    const chunk = data.subarray(i, i + 255);
    parts.push(Buffer.from([chunk.length]), chunk);
  }
  parts.push(Buffer.from([0]));
  return Buffer.concat(parts);
}

const u16 = (n) => Buffer.from([n & 255, (n >> 8) & 255]);

/** All frames must have the size of the first one. `delaysMs` has one entry per frame (default 100 ms). */
export function encodeGif(frames, { delaysMs = [], loop = 0 } = {}) {
  if (frames.length === 0) throw new Error("encodeGif: no frames");
  const { width, height } = frames[0];
  const parts = [
    Buffer.from("GIF89a"),
    u16(width),
    u16(height),
    Buffer.from([0xf7, 0, 0]), // global colour table, 256 entries
    palette(),
    Buffer.from([0x21, 0xff, 0x0b]),
    Buffer.from("NETSCAPE2.0"),
    Buffer.from([3, 1]),
    u16(loop),
    Buffer.from([0]),
  ];
  frames.forEach((f, n) => {
    if (f.width !== width || f.height !== height) throw new Error("encodeGif: frames differ in size");
    const px = new Uint8Array(width * height);
    for (let i = 0; i < px.length; i++) px[i] = paletteIndex(f.rgba[i * 4], f.rgba[i * 4 + 1], f.rgba[i * 4 + 2]);
    const delayCs = Math.max(2, Math.round((delaysMs[n] ?? 100) / 10));
    parts.push(
      Buffer.from([0x21, 0xf9, 4, 0x04]), // graphic control: leave in place, no transparency
      u16(delayCs),
      Buffer.from([0, 0]),
      Buffer.from([0x2c]),
      u16(0),
      u16(0),
      u16(width),
      u16(height),
      Buffer.from([0, 8]), // no local table, minimum code size 8
      subBlocks(lzw(px)),
    );
  });
  parts.push(Buffer.from([0x3b]));
  return Buffer.concat(parts);
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const [, , out, w, h, n, delay] = process.argv;
  const width = Number(w);
  const height = Number(h);
  const frames = [];
  for (let k = 0; k < Number(n); k++) {
    const rgba = new Uint8Array(width * height * 4);
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        const i = (y * width + x) * 4;
        // frame k: a red column sweeping right over a cream background
        const hot = x === Math.min(width - 1, k);
        rgba.set(hot ? [220, 40, 40, 255] : [255, 255, 170, 255], i);
      }
    }
    frames.push({ width, height, rgba });
  }
  writeFileSync(out, encodeGif(frames, { delaysMs: frames.map(() => Number(delay)) }));
}
