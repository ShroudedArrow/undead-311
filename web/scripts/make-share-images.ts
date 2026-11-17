// REQ-WEB-LINKS.2: render a share image per headline possible zombie and per neighborhood into dist/share/ (static files, no runtime service),
// plus a small stub page per image with Open Graph tags that redirects to the app view. Run after `vite build`.
// Chromium (Playwright) draws a 1200 by 630 template (src/lib/share.ts). When no browser can start the step is skipped with a notice,
// unless SHARE_IMAGES=required. SHARE_IMAGES=skip skips it (the end-to-end build); SHARE_LIMIT=<n> renders only the first n zombies.
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";
import {
  gapWords, neighborhoodImagePath, neighborhoodShareHtml, neighborhoodSummaries, shareSlug, stubHtml, zombieImagePath, zombieShareHtml, SHARE_H, SHARE_W, fill,
  type GapText, type ShareText,
} from "../src/lib/share.ts";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..");
const dist = join(root, "dist");
const mode = process.env.SHARE_IMAGES ?? "";
if (mode === "skip") {
  console.log("make-share-images: skipped (SHARE_IMAGES=skip)");
  process.exit(0);
}
if (!existsSync(dist)) {
  console.error("make-share-images: web/dist does not exist; run vite build first");
  process.exit(1);
}
const local = join(root, "..", ".local-data", "browsers");
if (!process.env.PLAYWRIGHT_BROWSERS_PATH && existsSync(local)) process.env.PLAYWRIGHT_BROWSERS_PATH = local;

const en = JSON.parse(readFileSync(join(root, "src", "copy", "en.json"), "utf8"));
const text: ShareText = { ...en.share, stamp_closed: en.card.stamp_closed, stamp_again: en.card.stamp_again };
const gap: GapText = en.card;
const families: Record<string, string> = en.families;
const label = (f: string) => families[f] ?? f;
const siteUrl = (process.env.SITE_URL ?? "").replace(/\/$/, "");

// zombies are sharded (zombies/<neighborhood>-<year>.json, REQ-EXP-SIZE.3): read every shard, not the index
const zombieDir = join(root, "public", "data", "zombies");
const zombies: { zombie_id: string; tier: string; type_family: string; neighborhood: string | null; gap_days: number }[] = existsSync(zombieDir)
  ? readdirSync(zombieDir).filter((f) => f.endsWith(".json") && f !== "index.json").sort().flatMap((f) => JSON.parse(readFileSync(join(zombieDir, f), "utf8")).zombies)
  : [];
const headline = zombies.filter((z) => z.tier === "headline").sort((a, b) => (a.zombie_id < b.zombie_id ? -1 : 1));
const limit = process.env.SHARE_LIMIT ? Number(process.env.SHARE_LIMIT) : Infinity;
const zs = headline.slice(0, limit);
const hoods = neighborhoodSummaries(headline, label);

const fontCss = (family: string, weight: number, file: string) =>
  `@font-face{font-family:"${family}";font-weight:${weight};src:url(data:font/woff2;base64,${readFileSync(join(root, "node_modules", "@fontsource", file)).toString("base64")}) format("woff2")}`;
const fonts = [
  fontCss("Public Sans", 400, "public-sans/files/public-sans-latin-400-normal.woff2"),
  fontCss("Public Sans", 700, "public-sans/files/public-sans-latin-700-normal.woff2"),
  fontCss("Courier Prime", 700, "courier-prime/files/courier-prime-latin-700-normal.woff2"),
].join("\n");

let browser;
try {
  browser = await chromium.launch();
} catch (e) {
  const msg = `make-share-images: no browser could start (${e instanceof Error ? e.message.split("\n")[0] : "unknown"})`;
  if (mode === "required") {
    console.error(msg);
    process.exit(1);
  }
  console.warn(`${msg}; share images were not rendered. Run \`npx playwright install chromium\` or set PLAYWRIGHT_BROWSERS_PATH.`);
  process.exit(0);
}
const page = await browser.newPage({ viewport: { width: SHARE_W, height: SHARE_H } });
const write = (rel: string, data: string | Buffer) => {
  const f = join(dist, rel);
  mkdirSync(dirname(f), { recursive: true });
  writeFileSync(f, data);
};
const shoot = async (html: string, rel: string) => {
  await page.setContent(html, { waitUntil: "load" });
  await page.evaluate(() => document.fonts.ready);
  write(rel, await page.screenshot({ type: "png", clip: { x: 0, y: 0, width: SHARE_W, height: SHARE_H } }));
};

for (const z of zs) {
  const where = fill(text.zombie_where, { family: label(z.type_family), neighborhood: z.neighborhood ?? text.unknown_neighborhood });
  const gapText = gapWords(z.gap_days, gap);
  await shoot(zombieShareHtml({ familyLabel: label(z.type_family), neighborhood: z.neighborhood ?? en.share.unknown_neighborhood, gap: gapText }, text, fonts), zombieImagePath(z.zombie_id));
  write(`share/zombie/${shareSlug(z.zombie_id)}.html`, stubHtml({ title: where, description: fill(text.zombie_line, { gap: gapText }), imageUrl: `${siteUrl}/${zombieImagePath(z.zombie_id)}`, target: `/zombie/${encodeURIComponent(z.zombie_id)}` }));
}
for (const h of hoods) {
  await shoot(neighborhoodShareHtml(h, text, fonts), neighborhoodImagePath(h.neighborhood));
  write(`share/neighborhood/${shareSlug(h.neighborhood)}.html`, stubHtml({ title: `${text.neighborhood_kicker} ${h.neighborhood}`, description: fill(text.neighborhood_line, { count: h.count }), imageUrl: `${siteUrl}/${neighborhoodImagePath(h.neighborhood)}`, target: `/neighborhood/${shareSlug(h.neighborhood)}` }));
}
await browser.close();
console.log(`make-share-images: ${zs.length} zombie images and ${hoods.length} neighborhood images -> dist/share/`);
