// REQ-WEB-LINKS.2: render share images only for real share targets into dist/share/ (static files, no runtime service): the home page
// (share/site.png, also the generic site image every other page falls back to through Open Graph tags in dist/index.html), the judge-mode
// tour's zombies, every neighborhood and every council district, each with a small stub page that carries Open Graph tags and redirects to
// the app view. No other possible zombie gets an image: the nightly build drew 19,066 of them (15 minutes, 38,000 files to upload).
// Run after `vite build`. Chromium (Playwright) draws a 1200 by 630 template (src/lib/share.ts). When no browser can start the step is
// skipped with a notice, unless SHARE_IMAGES=required. SHARE_IMAGES=skip skips it (the end-to-end build). SITE_URL (optional) makes the
// image addresses in the Open Graph tags absolute.
import { existsSync, mkdirSync, readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";
import {
  districtImagePath, districtShareHtml, gapWords, neighborhoodImagePath, neighborhoodShareHtml, progressLine, selectShareTargets, shareSlug, siteOgTags,
  siteShareHtml, SITE_IMAGE_PATH, stubHtml, zombieImagePath, zombieShareHtml, SHARE_H, SHARE_W, fill,
  type GapText, type ShareText, type ShareZombie,
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
const text: ShareText = { ...en.share, report_title: en.card.report_title, stamp_closed: en.card.stamp_closed, stamp_again: en.card.stamp_again };
const gap: GapText = en.card;
const families: Record<string, string> = en.families;
const label = (f: string) => families[f] ?? f;
const siteUrl = (process.env.SITE_URL ?? "").replace(/\/$/, "");

// zombies are sharded (zombies/<neighborhood>-<year>.json, REQ-EXP-SIZE.3): read every shard, not the index
const dataDir = join(root, "public", "data");
const zombieDir = join(dataDir, "zombies");
const zombies: ShareZombie[] = existsSync(zombieDir)
  ? readdirSync(zombieDir).filter((f) => f.endsWith(".json") && f !== "index.json").sort().flatMap((f) => JSON.parse(readFileSync(join(zombieDir, f), "utf8")).zombies)
  : [];
const readJson = (rel: string) => (existsSync(join(dataDir, rel)) ? JSON.parse(readFileSync(join(dataDir, rel), "utf8")) : null);
// judge mode reads the frozen copy of the tour when there is one (REQ-OPS-SNAP.2), so the images follow the same file
const tour = readJson("frozen/stats/judge_tour.json") ?? readJson("stats/judge_tour.json");
const tourIds: string[] = tour?.zombie_ids ?? [];
const targets = selectShareTargets(zombies, tourIds, label);
for (const id of targets.missingTour) console.warn(`make-share-images: tour zombie ${id} is in no zombie shard; no image for it`);
if (!tour) console.warn("make-share-images: no judge_tour.json; no tour images");
const districts: { district: string; count: number }[] = readJson("districts.json")?.districts ?? [];
const headlineCount = zombies.filter((z) => z.tier === "headline").length;
const hoods = targets.neighborhoods;
const total = 1 + targets.tour.length + hoods.length + districts.length;

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

let done = 0;
const started = Date.now();
const tick = () => {
  done += 1;
  if (done % 5 === 0 || done === total) console.log(progressLine(done, total, Date.now() - started));
};
const siteImage = `${siteUrl}/${SITE_IMAGE_PATH}`;

await shoot(siteShareHtml({ heroLine: en.app.hero_line, count: headlineCount }, text, fonts), SITE_IMAGE_PATH);
tick();
for (const z of targets.tour) {
  const where = fill(text.zombie_where, { family: label(z.type_family), neighborhood: z.neighborhood ?? text.unknown_neighborhood });
  const gapText = gapWords(z.gap_days, gap);
  await shoot(zombieShareHtml({ familyLabel: label(z.type_family), neighborhood: z.neighborhood ?? en.share.unknown_neighborhood, gap: gapText }, text, fonts), zombieImagePath(z.zombie_id));
  write(`share/zombie/${shareSlug(z.zombie_id)}.html`, stubHtml({ title: where, description: fill(text.zombie_line, { gap: gapText }), imageUrl: `${siteUrl}/${zombieImagePath(z.zombie_id)}`, target: `/zombie/${encodeURIComponent(z.zombie_id)}` }));
  tick();
}
for (const h of hoods) {
  await shoot(neighborhoodShareHtml(h, text, fonts), neighborhoodImagePath(h.neighborhood));
  write(`share/neighborhood/${shareSlug(h.neighborhood)}.html`, stubHtml({ title: `${text.neighborhood_kicker} ${h.neighborhood}`, description: fill(text.neighborhood_line, { count: h.count }), imageUrl: `${siteUrl}/${neighborhoodImagePath(h.neighborhood)}`, target: `/neighborhood/${shareSlug(h.neighborhood)}` }));
  tick();
}
for (const d of districts) {
  const title = `${text.district_kicker} ${d.district}`;
  await shoot(districtShareHtml(d, text, fonts), districtImagePath(d.district));
  write(`share/district/${shareSlug(d.district)}.html`, stubHtml({ title, description: fill(text.district_line, { count: d.count }), imageUrl: `${siteUrl}/${districtImagePath(d.district)}`, target: `/districts/${encodeURIComponent(d.district)}` }));
  tick();
}
await browser.close();

// the app shell names the generic site image, so a route with no stub page of its own (every other zombie, /methods, /street ...) still has one
const indexFile = join(dist, "index.html");
const shell = readFileSync(indexFile, "utf8");
if (!shell.includes('property="og:image"')) {
  writeFileSync(indexFile, shell.replace("</head>", `${siteOgTags(siteImage, en.app.title, en.app.hero_line)}</head>`));
}

const countFiles = (dir: string): number => readdirSync(dir).reduce((n, f) => (statSync(join(dir, f)).isDirectory() ? n + countFiles(join(dir, f)) : n + 1), 0);
console.log(`make-share-images: ${targets.tour.length} tour zombie, ${hoods.length} neighborhood and ${districts.length} district images, plus the site image -> dist/share/`);
console.log(`make-share-images: web/dist now holds ${countFiles(dist)} files`);
