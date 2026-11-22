// Review screenshots of every page at 1280 and 390 px. Usage: node scripts/_review-shots.mjs <distDir> <outDir> <port>
import { chromium } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import { preview } from "vite";
const [dist, out, port = "4175"] = process.argv.slice(2);
mkdirSync(out, { recursive: true });
const server = await preview({ build: { outDir: dist }, preview: { port: +port, strictPort: true, host: "localhost" } });
const base = `http://localhost:${port}`;
const sizes = { desktop: { width: 1280, height: 800 }, phone: { width: 390, height: 844 } };
const browser = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
const report = {};
try {
  for (const [sn, vp] of Object.entries(sizes)) {
    const ctx = await browser.newContext({ viewport: vp, reducedMotion: "reduce", isMobile: sn === "phone", hasTouch: sn === "phone" });
    const page = await ctx.newPage();
    const go = async (name, path, wait = 2500, full = false) => {
      await page.goto(base + path);
      await page.waitForTimeout(wait);
      await page.screenshot({ path: `${out}/${sn}-${name}.png`, fullPage: full });
      report[`${sn}-${name}`] = await page.evaluate(() => ({ h: document.documentElement.scrollHeight, w: document.documentElement.scrollWidth, iw: innerWidth }));
    };
    await go("home", "/", 4000);
    await go("home-table", "/?view=table", 12000);
    await go("scorecard", "/scorecard", 2500, true);
    await go("durability", "/durability", 2500, true);
    await go("methods", "/methods", 2500);
    await go("repeat", "/repeat", 3500);
    await go("repeat-full", "/repeat", 3500, true);
    await go("street-empty", "/street", 2000);
    await go("judge", "/judge", 2000);
    await go("timelapse", "/timelapse", 4000);
    await go("not-found", "/nope", 1500);
    // street result
    await page.goto(base + "/street"); await page.waitForTimeout(1500);
    await page.getByRole("searchbox").fill("Dorchester Ave"); await page.waitForTimeout(500);
    await page.locator(".street-results button").first().click(); await page.waitForTimeout(3500);
    await page.screenshot({ path: `${out}/${sn}-street-result.png` });
    await page.screenshot({ path: `${out}/${sn}-street-result-full.png`, fullPage: true });
    report[`${sn}-street-result`] = await page.evaluate(() => ({ h: document.documentElement.scrollHeight, w: document.documentElement.scrollWidth, iw: innerWidth, url: location.search }));
    // a card: first point from points.json
    const id = await page.evaluate(async () => { const j = await (await fetch("/data/points.json")).json(); return j.id ? j.id[0] : null; });
    if (id) {
      await go("card", `/zombie/${encodeURIComponent(id)}`, 4500);
      // the whole form: a tall window, so the panel shows every field. A card with four objections: collapsed, then after "Show more"
      const tall = await browser.newContext({ viewport: { width: vp.width, height: sn === "phone" ? 3600 : 2800 }, reducedMotion: "reduce", isMobile: sn === "phone", hasTouch: sn === "phone" });
      const tp = await tall.newPage();
      await tp.goto(base + `/zombie/${encodeURIComponent("101002680075:101003312697")}`); await tp.waitForTimeout(4500);
      await tp.locator(".card-host").screenshot({ path: `${out}/${sn}-card-form.png` });
      await tp.getByRole("button", { name: /^Show \d+ more$/ }).click(); await tp.waitForTimeout(300);
      await tp.locator(".card-host").screenshot({ path: `${out}/${sn}-card-form-expanded.png` });
      await tall.close();
    }
    // the judge tour's first card, with the stamp
    await page.goto(base + "/judge"); await page.waitForTimeout(1500);
    await page.getByRole("button", { name: "Start the tour" }).click(); await page.waitForTimeout(1500);
    await page.screenshot({ path: `${out}/${sn}-judge-step-1.png` });
    await ctx.close();
  }
} finally { await browser.close(); await server.close(); }
writeFileSync(`${out}/report.json`, JSON.stringify(report, null, 1));
console.log(JSON.stringify(report));
