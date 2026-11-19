/**
 * Map performance profile (REQ-WEB-PERF). Serves a built copy of the site, drives the home map (wheel zoom, drag pan) and the
 * time-lapse (play) in Chromium, and records: frame times (requestAnimationFrame gaps), long tasks (over 50 ms), a JS CPU profile of
 * the main thread (self time by function) and a Chrome trace file you can open in DevTools or ui.perfetto.dev.
 *
 *   npx vite build --minify false --outDir ../.local-data/profile/dist-NAME --emptyOutDir
 *   node scripts/profile-map.mjs --dist ../.local-data/profile/dist-NAME --label NAME [--points 12000] [--device desktop|phone|both]
 *
 * Output goes to .local-data/profile/<label>-<device>.json (and .trace.json). Headless Chromium here draws with SwiftShader (software
 * GL), so frame times include rasterization on the CPU and read worse than a real GPU would; long tasks and the JS profile are
 * not affected by that. Compare runs made the same way, not these numbers against a real phone.
 */
import { mkdirSync, writeFileSync, readFileSync, existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { preview } from "vite";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "..");
const arg = (name, def) => {
  const i = process.argv.indexOf(`--${name}`);
  return i > 0 ? process.argv[i + 1] : def;
};
const dist = resolve(root, arg("dist", "dist"));
const label = arg("label", "run");
const extra = Number(arg("points", "12000"));
const which = arg("device", "both");
const outDir = resolve(root, "..", ".local-data", "profile");
mkdirSync(outDir, { recursive: true });
const browsers = resolve(root, "..", ".local-data", "browsers");
if (!process.env.PLAYWRIGHT_BROWSERS_PATH && existsSync(browsers)) process.env.PLAYWRIGHT_BROWSERS_PATH = browsers;
// imported after the path is set: Playwright reads it when it loads
const { chromium, devices } = await import("@playwright/test");

/** Grow the committed points file to `n` rows: jittered copies, so the map has a realistic load. Deterministic. */
function inflate(file, n) {
  if (n === 0) {
    // basemap only: no markers, to measure what the basemap costs by itself
    const out = {};
    for (const k of Object.keys(file)) out[k] = Array.isArray(file[k]) ? [] : file[k];
    out.n = 0;
    return out;
  }
  if (!n || n <= file.n) return file;
  const out = {};
  for (const k of Object.keys(file)) out[k] = Array.isArray(file[k]) ? [] : file[k];
  let seed = 12345;
  const rnd = () => ((seed = (seed * 1664525 + 1013904223) >>> 0) / 2 ** 32);
  for (let i = 0; i < n; i++) {
    const j = i % file.n;
    for (const k of Object.keys(file)) {
      if (!Array.isArray(file[k])) continue;
      let v = file[k][j];
      if (i >= file.n) {
        if (k === "id") v = `${v}~${i}`;
        else if (k === "lat") v = Math.round((v + (rnd() - 0.5) * 0.05) * 1e6) / 1e6;
        else if (k === "lon") v = Math.round((v + (rnd() - 0.5) * 0.06) * 1e6) / 1e6;
      }
      out[k].push(v);
    }
  }
  out.n = n;
  return out;
}

const INIT = `
  window.__perf = { on: false, frames: [], long: [] };
  let last = 0;
  const tick = (now) => { if (window.__perf.on && last) window.__perf.frames.push(now - last); last = now; requestAnimationFrame(tick); };
  requestAnimationFrame(tick);
  try {
    new PerformanceObserver((l) => { if (window.__perf.on) for (const e of l.getEntries()) window.__perf.long.push(e.duration); }).observe({ entryTypes: ["longtask"] });
  } catch {}
`;

const pct = (a, p) => (a.length ? [...a].sort((x, y) => x - y)[Math.min(a.length - 1, Math.floor(p * a.length))] : 0);
const r1 = (x) => Math.round(x * 10) / 10;

function summarizeFrames(frames, long) {
  const over = (ms) => frames.filter((f) => f > ms).length;
  return {
    frames: frames.length,
    frame_ms_p50: r1(pct(frames, 0.5)),
    frame_ms_p95: r1(pct(frames, 0.95)),
    frame_ms_max: r1(Math.max(0, ...frames)),
    frames_over_33ms: over(33.4),
    frames_over_100ms: over(100),
    long_tasks: long.length,
    long_task_ms_total: r1(long.reduce((s, x) => s + x, 0)),
    long_task_ms_max: r1(Math.max(0, ...long)),
  };
}

/** Self time per function from a V8 CPU profile, top n. */
function topFunctions(profile, n = 14) {
  const byId = new Map(profile.nodes.map((nd) => [nd.id, nd]));
  const self = new Map();
  for (let i = 0; i < profile.samples.length; i++) {
    const nd = byId.get(profile.samples[i]);
    const dt = (profile.timeDeltas[i] ?? 0) / 1000;
    const cf = nd.callFrame;
    const key = `${cf.functionName || "(anonymous)"} ${cf.url.split("/").pop() || ""}:${cf.lineNumber + 1}`;
    self.set(key, (self.get(key) ?? 0) + dt);
  }
  const total = [...self.values()].reduce((s, x) => s + x, 0);
  const idle = (self.get("(idle) :1") ?? 0) + [...self].filter(([k]) => k.startsWith("(idle)")).reduce((s, [, v]) => s + v, 0) - (self.get("(idle) :1") ?? 0);
  // the chain of callers for the most expensive function, so the report can say who asked for it
  const parent = new Map();
  for (const nd of profile.nodes) for (const c of nd.children ?? []) parent.set(c, nd.id);
  const heavy = new Map();
  for (let i = 0; i < profile.samples.length; i++) heavy.set(profile.samples[i], (heavy.get(profile.samples[i]) ?? 0) + (profile.timeDeltas[i] ?? 0) / 1000);
  const topNode = [...heavy.entries()].filter(([id]) => !/^\((idle|program|root)\)/.test(byId.get(id).callFrame.functionName)).sort((a, b) => b[1] - a[1])[0];
  const stack = [];
  for (let id = topNode?.[0]; id !== undefined && stack.length < 12; id = parent.get(id)) stack.push(`${byId.get(id).callFrame.functionName || "(anonymous)"}:${byId.get(id).callFrame.lineNumber + 1}`);
  const native = (self.get("(program) :0") ?? 0) + (self.get("(garbage collector) :0") ?? 0);
  return {
    busy_ms: r1(total - idle),
    program_ms: r1(self.get("(program) :0") ?? 0),
    idle_ms: r1(idle),
    heaviest_stack: stack,
    native_ms: r1(native),
    top: [...self.entries()].filter(([k]) => !k.startsWith("(idle)") && !k.startsWith("(program)")).sort((a, b) => b[1] - a[1]).slice(0, n).map(([k, v]) => ({ fn: k, self_ms: r1(v) })),
  };
}

/** Main-thread and GPU-process totals from a Chrome trace (inclusive durations by event name; nested events overlap). */
function traceSummary(events) {
  const sum = new Map();
  for (const e of events) {
    if (e.ph !== "X" || !e.dur) continue;
    if (!["RunTask", "FunctionCall", "UpdateLayoutTree", "Layout", "Paint", "Commit", "MinorGC", "MajorGC", "V8.GC_MC_BACKGROUND_MARKING", "GPUTask", "RasterTask", "ImageDecodeTask", "CompositeLayers", "EvaluateScript", "FireAnimationFrame", "EventDispatch", "TimerFire", "HitTest", "Layerize"].includes(e.name)) continue;
    sum.set(e.name, (sum.get(e.name) ?? 0) + e.dur / 1000);
  }
  return Object.fromEntries([...sum.entries()].sort((a, b) => b[1] - a[1]).map(([k, v]) => [k, r1(v)]));
}

async function wait(ms) { await new Promise((r) => setTimeout(r, ms)); }

async function scenarioHome(page) {
  await page.goto("/", { waitUntil: "load" });
  await page.waitForSelector('[data-testid="map"][data-ready="true"]', { timeout: 60000 });
  await wait(1500);
  const box = await page.locator('[data-testid="map"]').boundingBox();
  const cx = box.x + box.width / 2;
  const cy = box.y + box.height / 2;
  await page.mouse.move(cx, cy);
  await page.evaluate(() => { window.__perf.frames.length = 0; window.__perf.long.length = 0; window.__perf.on = true; });
  // zoom in through the density threshold (13), pan around, zoom back out
  const phase = async (name) => page.evaluate((n) => window.__perf.marks.push([n, window.__perf.frames.length, window.__perf.long.length, document.querySelector('[data-testid="map"]')?.getAttribute("data-zoom")]), name);
  await page.evaluate(() => { window.__perf.marks = []; });
  await phase("zoom_in");
  for (let i = 0; i < 28; i++) { await page.mouse.wheel(0, -100); await wait(45); }
  await wait(600);
  await phase("pan");
  for (let k = 0; k < 4; k++) {
    await page.mouse.move(cx, cy); await page.mouse.down();
    await page.mouse.move(cx - 220, cy + 90, { steps: 25 });
    await page.mouse.move(cx + 40, cy - 60, { steps: 25 });
    await page.mouse.up();
    await wait(150);
  }
  await phase("zoom_out");
  for (let i = 0; i < 28; i++) { await page.mouse.wheel(0, 100); await wait(45); }
  await wait(800);
  const zoom = await page.locator('[data-testid="map"]').getAttribute("data-zoom");
  const frames = await page.evaluate(() => { window.__perf.on = false; return { f: window.__perf.frames.slice(), l: window.__perf.long.slice(), m: window.__perf.marks }; });
  const phases = {};
  frames.m.forEach(([name, f0, l0, z], i) => {
    const [, f1, l1] = frames.m[i + 1] ?? [null, frames.f.length, frames.l.length];
    const s = summarizeFrames(frames.f.slice(f0, f1), frames.l.slice(l0, l1));
    phases[name] = { start_zoom: z, p50: s.frame_ms_p50, p95: s.frame_ms_p95, long_tasks: s.long_tasks, long_task_ms_max: s.long_task_ms_max };
  });
  return { ...summarizeFrames(frames.f, frames.l), end_zoom: zoom, phases };
}

async function scenarioTimelapse(page) {
  await page.goto("/timelapse", { waitUntil: "load" });
  await page.waitForSelector('[data-testid="map"][data-ready="true"]', { timeout: 60000 }).catch(() => undefined);
  await wait(1500);
  if (extra === 0) return {};
  const play = page.getByRole("button", { name: /^play/i });
  await page.evaluate(() => { window.__perf.frames.length = 0; window.__perf.long.length = 0; window.__perf.on = true; });
  await play.click();
  await wait(12000);
  const shown = await page.locator('[data-testid="map"]').getAttribute("data-marker-count");
  const frames = await page.evaluate(() => { window.__perf.on = false; return { f: window.__perf.frames.slice(), l: window.__perf.long.slice() }; });
  return { ...summarizeFrames(frames.f, frames.l), markers_after_12s: shown };
}

async function run(device, server) {
  // --gl angle: GPU compositing on SwiftShader through ANGLE, as a GPU machine composites (no read-back of every WebGL frame).
  // --gl swiftshader: the flags playwright.config.ts uses, which composite in software and read each canvas back every frame.
  const gl = arg("gl", "swiftshader");
  const args = gl === "angle" ? ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist", "--enable-gpu-compositing"] : ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"];
  const browser = await chromium.launch({ args });
  const ctxOptions = device === "phone" ? { ...devices["Pixel 7"], baseURL: server } : { viewport: { width: 1280, height: 800 }, baseURL: server };
  const results = { device, label, points: extra, gl: arg("gl", "swiftshader") };
  for (const scenario of ["home", "timelapse"]) {
    const context = await browser.newContext(ctxOptions);
    await context.addInitScript(INIT);
    // the committed fixture has about 1,000 points; grow it so the map has a realistic load
    await context.route("**/data/points.json", async (route) => {
      const res = await route.fetch();
      const body = await res.json();
      await route.fulfill({ response: res, json: inflate(body, extra) });
    });
    const page = await context.newPage();
    const cdp = await context.newCDPSession(page);
    // A mid-range phone: Pixel 7 screen and pixel ratio, with the CPU slowed 4x. The desktop run is not throttled.
    if (device === "phone") await cdp.send("Emulation.setCPUThrottlingRate", { rate: 4 });
    await cdp.send("Profiler.enable");
    await cdp.send("Profiler.setSamplingInterval", { interval: 500 });
    await browser.startTracing(page, { categories: ["devtools.timeline", "v8", "gpu", "cc", "viz", "blink.user_timing"] });
    await cdp.send("Profiler.start");
    const metrics = scenario === "home" ? await scenarioHome(page) : await scenarioTimelapse(page);
    const { profile } = await cdp.send("Profiler.stop");
    const trace = JSON.parse((await browser.stopTracing()).toString());
    const events = Array.isArray(trace) ? trace : trace.traceEvents;
    results[scenario] = { ...metrics, js: topFunctions(profile), trace_ms: traceSummary(events) };
    writeFileSync(join(outDir, `${label}-${device}-${scenario}.trace.json`), JSON.stringify(events.filter((e) => e.ph === "X" && e.dur > 1000)));
    await context.close();
  }
  await browser.close();
  return results;
}

const server = await preview({ root, build: { outDir: dist }, preview: { port: 4179, strictPort: true, host: "127.0.0.1" } });
const base = "http://127.0.0.1:4179";
try {
  for (const device of which === "both" ? ["desktop", "phone"] : [which]) {
    const res = await run(device, base);
    writeFileSync(join(outDir, `${label}-${device}.json`), JSON.stringify(res, null, 2));
    console.log(JSON.stringify({ device, home: { ...res.home, js: undefined, trace_ms: undefined }, timelapse: { ...res.timelapse, js: undefined, trace_ms: undefined } }, null, 1));
  }
} finally {
  await new Promise((r) => server.httpServer.close(r));
}
