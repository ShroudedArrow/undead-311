// Captures the Devpost media from a LIVE deploy (not a local build): screenshots of every page at 1280 px and 390 px,
// three looping GIF clips (each under 10 s), and 3:2 gallery versions. Output goes to docs/media/.
//
//   node ops/capture/live.mjs --base https://undead311.netlify.app [--only screenshots|clips|gallery] [--gallery a,b,c,d,e]
//
// Uses the page list in capture.config.json only. The Playwright browser comes from
// .local-data/browsers when present (same fallback as capture.mjs). Third-party logos are hidden; the OpenStreetMap
// attribution is kept (tech.md).
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..", "..");
const config = JSON.parse(readFileSync(join(here, "capture.config.json"), "utf8"));
const require = createRequire(join(root, "web", "package.json"));
const { chromium, devices } = require("@playwright/test");

const arg = (name, dflt) => {
  const i = process.argv.indexOf(name);
  return i >= 0 ? process.argv[i + 1] : dflt;
};
const base = arg("--base", "https://undead311.netlify.app").replace(/\/$/, "");
const only = arg("--only");
const want = (w) => !only || only === w;
const out = join(root, config.out_dir);

const localBrowsers = join(root, ".local-data", "browsers");
if (!process.env.PLAYWRIGHT_BROWSERS_PATH && existsSync(localBrowsers)) process.env.PLAYWRIGHT_BROWSERS_PATH = localBrowsers;
const launchOptions = { args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] };

/** The Stuart St and Kneeland St card (REQ-OPS-CAPTURE). It has a Second opinion with verdict "survives". */
const CARD_ID = "101002329140:101002356770";
const CARD_NEIGHBORHOOD = "downtown-financial-district";
const CARD_DISTRICT = "1C";

const VIEWPORTS = [
  { name: "desktop", width: 1280, height: 800, mobile: false },
  { name: "phone", width: 390, height: 844, mobile: true },
];

const fill = (p) =>
  p
    .replace("{first_zombie}", encodeURIComponent(CARD_ID))
    .replace("{first_neighborhood}", CARD_NEIGHBORHOOD)
    .replace("{first_district}", CARD_DISTRICT);

// Not the not-found page: on the live site an unknown URL gets Netlify's own 404 page, not the app's NotFound route.
const PAGES = config.pages;

function ctxOptions(vp, height = vp.height, scale) {
  const base = vp.mobile ? { ...devices["Pixel 7"] } : {};
  const o = { ...base, viewport: { width: vp.width, height }, reducedMotion: "no-preference" };
  if (scale) o.deviceScaleFactor = scale;
  return o;
}

async function hideLogos(page) {
  const css = config.hide_selectors.map((s) => `${s} { visibility: hidden !important; }`).join("\n");
  await page.addStyleTag({ content: css });
}

async function open(page, p) {
  await page.goto(base + fill(p.path), { waitUntil: "load" });
  await page.waitForSelector(p.wait, { state: "visible", timeout: 60_000 });
  await page.waitForLoadState("networkidle").catch(() => {});
  await page.waitForTimeout(1500); // map tiles and layers settle
  await hideLogos(page);
}

async function screenshots(browser) {
  const dir = join(out, "screenshots");
  mkdirSync(dir, { recursive: true });
  const files = [];
  for (const vp of VIEWPORTS) {
    const ctx = await browser.newContext(ctxOptions(vp));
    const page = await ctx.newPage();
    for (const p of PAGES) {
      await open(page, p);
      const file = join(dir, `${vp.name}-${p.name}.png`);
      await page.screenshot({ path: file });
      files.push(file);
    }
    await ctx.close();
  }
  return files;
}

const GIF_WIDTH = 800;
const FRAME_MS = 200;
const python = existsSync(join(root, ".local-data", "venv", "bin", "python")) ? join(root, ".local-data", "venv", "bin", "python") : "python3";

/** Runs `step(i, n)` for each of n frames, shoots after it, and writes a looping GIF (n * FRAME_MS < 10 s) through
 * assemble_gif.py (Pillow), which gives the clip one adaptive palette. */
async function makeGif(browser, name, n, setup, step, shoot, holdLastMs = 1500) {
  if ((n - 1) * FRAME_MS + holdLastMs >= 10_000) throw new Error(`${name}: clip would reach 10 s`);
  const ctx = await browser.newContext(ctxOptions(VIEWPORTS[0]));
  const page = await ctx.newPage();
  const tmp = join(root, ".local-data", "gif-frames", name);
  rmSync(tmp, { recursive: true, force: true });
  mkdirSync(tmp, { recursive: true });
  await setup(page);
  const paths = [];
  for (let i = 0; i < n; i++) {
    await step(page, i, n);
    const f = join(tmp, String(i).padStart(3, "0") + ".png");
    writeFileSync(f, await shoot(page));
    paths.push(f);
  }
  await ctx.close();
  const file = join(out, "clips", `${name}.gif`);
  mkdirSync(dirname(file), { recursive: true });
  execFileSync(python, [join(here, "assemble_gif.py"), file, String(GIF_WIDTH), String(FRAME_MS), String(holdLastMs), ...paths]);
  return file;
}

async function clips(browser) {
  const files = [];
  const map = config.pages.find((p) => p.name === "map");
  const lapse = config.pages.find((p) => p.name === "timelapse");

  // 1. Home map from city to street: wheel-zoom at downtown, next to Stuart St and Kneeland St.
  files.push(
    await makeGif(
      browser,
      "home-map-zoom",
      36,
      async (page) => {
        await open(page, map);
        await page.mouse.move(790, 372);
      },
      async (page, i) => {
        if (i > 0) await page.mouse.wheel(0, -240);
        await page.waitForTimeout(600);
      },
      (page) => page.screenshot(),
    ),
  );

  // 2. Night of the Living 311: scrub the time-lapse from its start to its end (the slider is deterministic; real-time play is not).
  files.push(
    await makeGif(
      browser,
      "night-of-the-living-311",
      40,
      async (page) => {
        await open(page, lapse);
      },
      async (page, i, n) => {
        await page.locator(".timelapse-controls input[type=range]").fill(String(Math.round((i / (n - 1)) * 1000)));
        await page.waitForTimeout(500);
      },
      (page) => page.screenshot(),
    ),
  );

  // 3. The Stuart St and Kneeland St card: opens over the map (client-side route), then scrolls to the Second opinion.
  files.push(
    await makeGif(
      browser,
      "autopsy-card-second-opinion",
      36,
      async (page) => {
        await open(page, map);
      },
      async (page, i, n) => {
        if (i === 1) {
          await page.evaluate((id) => {
            history.pushState({}, "", "/zombie/" + encodeURIComponent(id));
            window.dispatchEvent(new PopStateEvent("popstate"));
          }, CARD_ID);
          await page.waitForSelector("[data-testid=autopsy-card]", { state: "visible", timeout: 60_000 });
          await page.waitForTimeout(1500);
          await hideLogos(page);
        } else if (i > 8) {
          // scroll the card's own scroll container down to the Second opinion, in even steps
          await page.evaluate((k) => {
            const so = document.querySelector("[data-testid=second-opinion]");
            let el = so.parentElement;
            while (el && !/(auto|scroll)/.test(getComputedStyle(el).overflowY)) el = el.parentElement;
            const target = so.getBoundingClientRect().top - el.getBoundingClientRect().top + el.scrollTop - 12;
            el.scrollTo({ top: (target * k) / 20, behavior: "instant" });
          }, Math.min(i - 8, 20));
        }
        await page.waitForTimeout(250);
      },
      (page) => page.screenshot(),
      2500,
    ),
  );
  return files;
}

/** 3:2 gallery versions: the page is rendered in a 1200 x 800 viewport (exactly 3:2; nothing is cropped) at 2x, so
 * the images are 2400 x 1600, then checked against the 5 MB limit. */
const GALLERY_DEFAULT = "map,card,timelapse,repeat,scorecard";
const GALLERY_LIMIT = 5 * 1024 * 1024;
async function gallery(browser) {
  const names = arg("--gallery", GALLERY_DEFAULT).split(",");
  const dir = join(out, "gallery");
  mkdirSync(dir, { recursive: true });
  const ctx = await browser.newContext(ctxOptions({ ...VIEWPORTS[0], width: 1200 }, 800, 2));
  const page = await ctx.newPage();
  const files = [];
  for (const [i, name] of names.entries()) {
    const p = PAGES.find((x) => x.name === name);
    if (!p) throw new Error(`gallery: no page named ${name}`);
    await open(page, p);
    const file = join(dir, `${String(i + 1).padStart(2, "0")}-${name}-3x2.png`);
    await page.screenshot({ path: file });
    if (statSync(file).size >= GALLERY_LIMIT) throw new Error(`${file} is over 5 MB`);
    files.push(file);
  }
  await ctx.close();
  return files;
}

mkdirSync(out, { recursive: true });
const browser = await chromium.launch(launchOptions);
const written = [];
try {
  if (want("screenshots")) written.push(...(await screenshots(browser)));
  if (want("clips")) written.push(...(await clips(browser)));
  if (want("gallery")) written.push(...(await gallery(browser)));
} finally {
  await browser.close();
}
for (const f of written) console.log("live: wrote", f.replace(root + "/", ""), statSync(f).size);
