// Writes public/favicon.svg: the map's own spray-paint circle (src/map/sprites.ts, seeded, no randomness) with a stencil U inside, in the
// spray-stencil style of the zombie markers. Run `node scripts/make-favicon.ts` after changing the sprites. The output is committed.
import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { PALETTE } from "../src/map/palette.ts";
import { spraySvg } from "../src/map/sprites.ts";

const ring = spraySvg(1, 64).replace(' aria-hidden="true" focusable="false"', "");
const letter = `<path d="M23 19V38Q23 47 32 47Q41 47 41 38V19" fill="none" stroke="${PALETTE.asphalt}" stroke-width="6.5" stroke-linejoin="round"/>`;
const svg = ring.replace("</svg>", `${letter}</svg>`);
writeFileSync(join(dirname(fileURLToPath(import.meta.url)), "..", "public", "favicon.svg"), svg + "\n");
console.log(`make-favicon: wrote public/favicon.svg (${svg.length} bytes)`);
