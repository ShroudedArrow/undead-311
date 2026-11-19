import { chromium } from "@playwright/test";
import { preview } from "vite";
const server = await preview({ preview: { port: 4177, strictPort: true, host: "localhost" } });
const b = await chromium.launch();
const res = {};
for (const w of [320, 390, 800, 1280]) {
  for (const path of ["/scorecard", "/methods", "/durability"]) {
    const page = await (await b.newContext({ viewport: { width: w, height: 900 } })).newPage();
    await page.goto("http://localhost:4177" + path); await page.waitForTimeout(2500);
    const hs = await page.evaluate(() => Object.fromEntries([...document.querySelectorAll("[data-slot]")].map((e) => [e.dataset.slot, +(e.getBoundingClientRect().height / parseFloat(getComputedStyle(document.documentElement).fontSize)).toFixed(1)])));
    for (const [k, v] of Object.entries(hs)) (res[k] ??= {})[w] = v;
    await page.close();
  }
}
console.log(JSON.stringify(res, null, 1));
await b.close(); await server.close();
