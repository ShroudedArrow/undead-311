// Before/after screenshots and layout measurements for the UI polish PR.
// Usage: node scripts/ui-shots.mjs <before|after>   (needs a built web/dist; starts its own preview server)
import { chromium } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import { preview } from "vite";

const tag = process.argv[2] ?? "after";
const out = new URL("../../docs/screenshots/ui-polish/", import.meta.url).pathname;
mkdirSync(out, { recursive: true });
const server = await preview({ preview: { port: 4174, strictPort: true, host: "localhost" } });
const base = "http://localhost:4174";
const sizes = { desktop: { width: 1280, height: 800 }, phone: { width: 390, height: 844 } };
const pages = { map: "/", methods: "/methods", timelapse: "/timelapse", scorecard: "/scorecard" };
const browser = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
const report = {};
const ready = (page) => page.waitForSelector("[data-testid=map][data-ready=true]", { timeout: 30000 }).catch(() => {});
try {
  for (const [sn, vp] of Object.entries(sizes)) {
    const ctx = await browser.newContext({ viewport: vp, deviceScaleFactor: 1, hasTouch: sn === "phone", isMobile: sn === "phone" });
    const page = await ctx.newPage();
    for (const [pn, path] of Object.entries(pages)) {
      await page.addInitScript(() => {
        window.__cls = 0;
        new PerformanceObserver((l) => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__cls += e.value; }).observe({ type: "layout-shift", buffered: true });
      });
      await page.goto(base + path);
      if (pn === "map" || pn === "timelapse") await ready(page);
      await page.waitForTimeout(2500);
      await page.screenshot({ path: `${out}${tag}-${sn}-${pn}.png` });
      report[`${sn}-${pn}`] = await page.evaluate(() => ({ scrollH: document.documentElement.scrollHeight, innerH: innerHeight, scrollW: document.documentElement.scrollWidth, innerW: innerWidth, cls: +(window.__cls ?? 0).toFixed(3) }));
    }
    // layout stability: sample the map's box every 100 ms while the page loads; every change after the first is a shift
    await page.goto(base + "/", { waitUntil: "commit" });
    const seen = [];
    for (let i = 0; i < 40; i++) {
      const b = await page.getByTestId("map").boundingBox().catch(() => null);
      const key = b ? JSON.stringify([b.x, b.y, b.width, b.height].map(Math.round)) : null;
      if (key && seen[seen.length - 1] !== key) seen.push(key);
      await page.waitForTimeout(100);
    }
    report[`${sn}-map-box-changes`] = seen;
    await ready(page);
    // the density view at city zoom (the map shot above) and the stencil markers two zoom steps in
    await page.waitForTimeout(600);
    for (let i = 0; i < 2; i++) { await page.getByRole("button", { name: "Zoom in" }).click(); await page.waitForTimeout(800); }
    await page.screenshot({ path: `${out}${tag}-${sn}-map-zoomed.png` });
    report[`${sn}-map-zoomed`] = await page.getByTestId("map").evaluate((e) => ({ zoom: e.dataset.zoom, clusters: e.dataset.clusterCount }));
    await page.goto(base + "/");
    await ready(page);
    const toggle = page.getByRole("button", { name: /show filters/i });
    if (await toggle.isVisible()) await toggle.click();
    const rect = () => page.getByTestId("map").boundingBox();
    const before = await rect();
    await page.locator(".filter-group summary, .filter-trigger").first().click();
    await page.waitForTimeout(400);
    const after = await rect();
    await page.screenshot({ path: `${out}${tag}-${sn}-filter-open.png` });
    report[`${sn}-filter`] = { before, after, moved: JSON.stringify(before) !== JSON.stringify(after) };
    await ctx.close();
  }
} finally {
  await browser.close();
  await server.close();
}
writeFileSync(`${out}${tag}-layout.json`, JSON.stringify(report, null, 1));
console.log(JSON.stringify(report, null, 1));
