// `make capture` (REQ-OPS-CAPTURE.1, REQ-OPS-CAPTURE.2): records the judge-mode tour as video, screenshots every page at
// desktop and phone sizes, and renders the time-lapse as a GIF, all into docs/media/ from the built site.
//
//   node ops/capture/capture.mjs [--base http://localhost:4174] [--only screenshots|video|gif]
//
// Without --base it serves web/dist with `vite preview` (run `make build` first). Playwright comes from web/node_modules.
// Third-party logos (the MapLibre logo and anything matching hide_selectors in capture.config.json) are hidden before every
// screenshot and the video starts; the OpenStreetMap attribution is kept (tech.md).
import { spawn } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, readdirSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { encodeGif } from "./gif.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..", "..");
const web = join(root, "web");
const config = JSON.parse(readFileSync(join(here, "capture.config.json"), "utf8"));
const out = join(root, config.out_dir);
const require = createRequire(join(web, "package.json"));
const { chromium, devices } = require("@playwright/test");

const arg = (name) => {
  const i = process.argv.indexOf(name);
  return i >= 0 ? process.argv[i + 1] : undefined;
};
const only = arg("--only");
const want = (what) => !only || only === what;

// Same self-correcting browser path as web/playwright.config.ts.
const localBrowsers = join(root, ".local-data", "browsers");
if (!process.env.PLAYWRIGHT_BROWSERS_PATH && existsSync(localBrowsers)) process.env.PLAYWRIGHT_BROWSERS_PATH = localBrowsers;
const launchOptions = { args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] };

const slug = (s) => (s || "unknown").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

/** Fills {first_zombie}, {first_neighborhood} and {first_district} from the served data, so the dynamic pages exist in any
 * dataset. When no headline zombie has a council district (the sample data), {first_district} falls back to "1" and the
 * page shows its "not found" state, which is still a page of the site (ops#205). */
function resolvePath(path) {
  // zombies are sharded (REQ-EXP-SIZE.3): read the shards, in file order
  const dir = join(web, "public", "data", "zombies");
  const zombies = readdirSync(dir).filter((f) => f.endsWith(".json") && f !== "index.json").sort()
    .flatMap((f) => JSON.parse(readFileSync(join(dir, f), "utf8")).zombies);
  const first = zombies[0];
  if (!first) throw new Error("capture: the zombies/ shards have no zombies");
  const withDistrict = zombies.find((z) => z.tier === "headline" && z.district);
  return path
    .replace("{first_zombie}", encodeURIComponent(first.zombie_id))
    .replace("{first_neighborhood}", slug(first.neighborhood))
    .replace("{first_district}", encodeURIComponent(withDistrict ? withDistrict.district : "1"));
}

/** Hides third-party logos and city marks. The attribution selectors in keep_selectors are never hidden. */
async function hideLogos(page) {
  const css = config.hide_selectors.map((s) => `${s} { visibility: hidden !important; }`).join("\n");
  await page.addStyleTag({ content: css });
}

async function startServer() {
  const given = arg("--base");
  if (given) return { base: given, stop: () => {} };
  if (!existsSync(join(web, "dist", "index.html"))) throw new Error("capture: web/dist is missing; run `make build` first");
  const port = 4174;
  const child = spawn("npx", ["vite", "preview", "--port", String(port), "--strictPort"], { cwd: web, stdio: "ignore" });
  const base = `http://localhost:${port}`;
  for (let i = 0; i < 60; i++) {
    try {
      if ((await fetch(base)).ok) return { base, stop: () => child.kill() };
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  child.kill();
  throw new Error("capture: vite preview did not start");
}

function contextOptions(vp) {
  const base = vp.device ? { ...devices[vp.device] } : {};
  return { ...base, viewport: { width: vp.width, height: vp.height }, reducedMotion: "no-preference" };
}

async function openPage(page, base, p) {
  await page.goto(base + resolvePath(p.path), { waitUntil: "load" });
  await page.waitForSelector(p.wait, { state: "visible", timeout: 30_000 });
  await page.waitForLoadState("networkidle").catch(() => {});
  await hideLogos(page);
}

async function screenshots(browser, base) {
  const dir = join(out, "screenshots");
  mkdirSync(dir, { recursive: true });
  const written = [];
  for (const vp of config.viewports) {
    const ctx = await browser.newContext(contextOptions(vp));
    const page = await ctx.newPage();
    for (const p of config.pages) {
      await openPage(page, base, p);
      const file = join(dir, `${vp.name}-${p.name}.png`);
      await page.screenshot({ path: file });
      written.push(file);
    }
    await ctx.close();
  }
  return written;
}

async function judgeVideo(browser, base) {
  const vp = config.viewports[0];
  const tmp = join(out, ".video-tmp");
  rmSync(tmp, { recursive: true, force: true });
  mkdirSync(tmp, { recursive: true });
  const ctx = await browser.newContext({ ...contextOptions(vp), recordVideo: { dir: tmp, size: { width: vp.width, height: vp.height } } });
  const page = await ctx.newPage();
  const pause = () => page.waitForTimeout(config.video.step_ms);
  await page.goto(base + "/", { waitUntil: "load" });
  await page.waitForSelector("[data-testid=map][data-ready=true]", { timeout: 30_000 });
  await hideLogos(page);
  await pause();
  await page.goto(base + "/judge", { waitUntil: "load" });
  await hideLogos(page);
  await pause();
  await page.getByRole("button", { name: "Start the tour" }).click();
  for (let n = 1; n <= 3; n++) {
    await page.getByTestId("autopsy-card").waitFor({ state: "visible", timeout: 30_000 });
    await hideLogos(page);
    await pause();
    await page.keyboard.press("ArrowRight");
  }
  await page.getByTestId("tour-done").waitFor({ state: "visible", timeout: 30_000 });
  await pause();
  const video = page.video();
  await ctx.close();
  const file = join(out, config.video.file);
  renameSync(await video.path(), file);
  rmSync(tmp, { recursive: true, force: true });
  return file;
}

/** Decodes a PNG to RGBA inside the browser (no PNG library needed), scaled to the given width. */
async function decode(helper, png, width) {
  const r = await helper.evaluate(async ({ b64, width: w }) => {
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    const bmp = await createImageBitmap(new Blob([bytes], { type: "image/png" }));
    const scale = Math.min(1, w / bmp.width);
    const cw = Math.max(1, Math.round(bmp.width * scale));
    const ch = Math.max(1, Math.round(bmp.height * scale));
    const canvas = document.createElement("canvas");
    canvas.width = cw;
    canvas.height = ch;
    const c2d = canvas.getContext("2d");
    c2d.drawImage(bmp, 0, 0, cw, ch);
    const data = c2d.getImageData(0, 0, cw, ch).data;
    let bin = "";
    for (let i = 0; i < data.length; i += 0x8000) bin += String.fromCharCode(...data.subarray(i, i + 0x8000));
    return { width: cw, height: ch, b64: btoa(bin) };
  }, { b64: png.toString("base64"), width });
  return { width: r.width, height: r.height, rgba: new Uint8Array(Buffer.from(r.b64, "base64")) };
}

async function timelapseGif(browser, base) {
  const g = config.gif;
  const vp = config.viewports[0];
  const ctx = await browser.newContext(contextOptions(vp));
  const page = await ctx.newPage();
  const helper = await ctx.newPage();
  await helper.goto("about:blank");
  await page.goto(base + "/timelapse", { waitUntil: "load" });
  await page.waitForSelector("[data-testid=timelapse-now]", { state: "visible", timeout: 30_000 });
  await page.waitForSelector(".timelapse-map [data-ready=true], .timelapse-map canvas", { timeout: 30_000 });
  await hideLogos(page);
  const slider = page.locator(".timelapse-controls input[type=range]");
  const map = page.locator(".timelapse-map");
  const frames = [];
  for (let i = 0; i < g.frames; i++) {
    await slider.fill(String(Math.round((i / (g.frames - 1)) * 1000)));
    await page.waitForTimeout(500);
    const png = await map.screenshot();
    frames.push(await decode(helper, png, g.width));
  }
  await ctx.close();
  const delaysMs = frames.map((_, i) => (i === frames.length - 1 ? g.last_delay_ms : g.delay_ms));
  const file = join(out, g.file);
  writeFileSync(file, encodeGif(frames, { delaysMs }));
  return file;
}

mkdirSync(out, { recursive: true });
const { base, stop } = await startServer();
const browser = await chromium.launch(launchOptions);
const written = [];
try {
  if (want("screenshots")) written.push(...(await screenshots(browser, base)));
  if (want("video")) written.push(await judgeVideo(browser, base));
  if (want("gif")) written.push(await timelapseGif(browser, base));
} finally {
  await browser.close();
  stop();
}
for (const f of written) console.log("capture: wrote", f.replace(root + "/", ""));
