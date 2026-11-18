import { chromium } from "@playwright/test";
import { preview } from "vite";
const server = await preview({ preview: { port: 4176, strictPort: true, host: "localhost" } });
const b = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
const only = process.argv[2];
for (const [name, vp] of [["1280", { width: 1280, height: 800 }], ["390", { width: 390, height: 844 }], ["320", { width: 320, height: 640 }]]) {
  for (const path of ["/", "/scorecard", "/methods", "/durability", "/timelapse"]) {
    if (only && !path.startsWith(only)) continue;
    const page = await (await b.newContext({ viewport: vp })).newPage();
    await page.addInitScript(() => {
      window.__cls = 0; window.__src = [];
      new PerformanceObserver((l) => { for (const e of l.getEntries()) if (!e.hadRecentInput) { window.__cls += e.value; for (const s of e.sources ?? []) window.__src.push(`${(s.node?.nodeName ?? "?")}.${(s.node?.className?.toString?.() ?? "").slice(0, 30)}|${(s.node?.id ?? "")} ${Math.round(s.previousRect.height)}->${Math.round(s.currentRect.height)}`); } }).observe({ type: "layout-shift", buffered: true });
    });
    await page.goto("http://localhost:4176" + path); await page.waitForTimeout(3500);
    const r = await page.evaluate(() => ({ cls: window.__cls, src: [...new Set(window.__src)].slice(0, 8) }));
    console.log(name, path, r.cls.toFixed(3), JSON.stringify(r.src));
    await page.close();
  }
}
await b.close(); await server.close();
