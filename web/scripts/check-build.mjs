// REQ-WEB-PERF.1-2: post-build checks on web/dist.
//  1. Origin check (fails the build): no page, style or script may point at another origin that the browser could fetch.
//     Text files are scanned for absolute URLs; every host must be on the reviewed INERT list (namespaces, documentation
//     links, link-only references, and library defaults that are never requested). A new host fails the build until a
//     person reviews it. The e2e test "makes no request to another origin" proves nothing is fetched at run time.
//  2. First-view payload: gzip size of what "/" loads, against the 3 MB budget. A failure under --strict, which `npm run build`
//     uses now that the engine shards its card files (REQ-WEB-PERF.1).
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, extname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";

const here = dirname(fileURLToPath(import.meta.url));
const dist = join(here, "..", "dist");
const strict = process.argv.includes("--strict");
const BUDGET_BYTES = 3 * 1024 * 1024;

/** Hosts that appear in the bundle as inert strings. Reviewed once; add with a reason. */
export const INERT_HOSTS = new Map([
  ["www.w3.org", "XML and SVG namespace strings"],
  ["undead-311", "JSON Schema $id values inside generated validators (not a real host)"],
  ["json-schema.org", "JSON Schema $schema strings"],
  ["github.com", "library error messages and our own link text"],
  ["en.wikipedia.org", "library documentation comments"],
  ["unpkg.com", "loaders.gl default CDN for optional workers; never requested, IconLayer is given a canvas, and the CSP blocks it"],
  ["reactrouter.com", "React Router error messages"],
  ["react.dev", "React error messages"],
  ["maplibre.org", "MapLibre documentation links in messages"],
  ["maplibre.invalid", "MapLibre URL parsing base (reserved invalid domain)"],
  ["localhost", "library development fallbacks"],
  ["www.openstreetmap.org", "OpenStreetMap copyright link in the footer (a link, not a request)"],
  ["wiki.openstreetmap.org", "documentation link in the basemap library"],
  ["deck.gl", "deck.gl documentation links in messages"],
  ["311.boston.gov", "link text template for the city's public case pages (a link, not a request)"],
]);

function walk(dir) {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
}

const TEXT = new Set([".html", ".js", ".mjs", ".css", ".json", ".svg", ".txt", ".webmanifest"]);

export function findHosts(text) {
  const hosts = new Set();
  for (const m of text.matchAll(/(?:https?:)?\/\/([a-zA-Z0-9][a-zA-Z0-9.-]*)(?::\d+)?(?=[/"'`)\s?#<>,;]|$)/g)) {
    const url = m[0];
    if (!/^https?:/.test(url)) continue; // protocol-relative strings are mostly regex or comments; checked in HTML below
    hosts.add(m[1]);
  }
  return hosts;
}

/** Markup that makes the browser fetch another origin: <script|link|img|source|iframe src/href>, css url(), @import. */
export function findFetchRefs(text, ext) {
  const refs = [];
  if (ext === ".html") for (const m of text.matchAll(/<(?:script|link|img|source|iframe|video|audio)\b[^>]*?\b(?:src|href)=["']((?:https?:)?\/\/[^"']+)["']/gi)) refs.push(m[1]);
  if (ext === ".css" || ext === ".html") {
    for (const m of text.matchAll(/url\(\s*["']?((?:https?:)?\/\/[^)"']+)/gi)) refs.push(m[1]);
    for (const m of text.matchAll(/@import\s+(?:url\()?\s*["']?((?:https?:)?\/\/[^)"';]+)/gi)) refs.push(m[1]);
  }
  return refs;
}

export function checkOrigins(files) {
  const problems = [];
  for (const [file, text] of files) {
    const ext = extname(file);
    for (const ref of findFetchRefs(text, ext)) problems.push(`${file}: fetches ${ref}`);
    if (ext === ".json" && file.includes("/data/")) continue; // case data may quote URLs in closure text
    for (const h of findHosts(text)) if (!INERT_HOSTS.has(h)) problems.push(`${file}: unreviewed host ${h}`);
  }
  return problems;
}

/** REQ-WEB-PERF.1: over the 3 MB budget is a build failure under --strict, a warning otherwise. */
export function budgetVerdict(totalBytes, strictMode) {
  const over = totalBytes > BUDGET_BYTES;
  return { over, fail: over && strictMode };
}

/**
 * REQ-WEB-FRESH.3 (UX-21, ops#70): the "Report an error" link must be a real https address, never a placeholder. The build cannot
 * check that the repository is public (it runs offline); the owner confirms that. Returns a list of problems.
 */
export function reportUrlProblems(url) {
  if (typeof url !== "string" || url.trim() === "") return ["links.report_error_url is empty"];
  const probe = url.replace(/\{[a-z_]+\}/g, "x");
  let u;
  try { u = new URL(probe); } catch { return [`links.report_error_url is not a URL: ${url}`]; }
  const problems = [];
  if (u.protocol !== "https:") problems.push("links.report_error_url must use https");
  if (/(^|\.)(example\.(com|org|net)|localhost|invalid|test)$/i.test(u.hostname)) problems.push(`links.report_error_url host is a placeholder: ${u.hostname}`);
  if (/todo|changeme|your[-_]?(org|repo|name)|<[^>]*>|\bowner\b\/\brepo\b/i.test(url)) problems.push("links.report_error_url still holds placeholder text");
  return problems;
}

function gz(path) {
  return gzipSync(readFileSync(path)).length;
}

export function firstViewFiles() {
  // Upper bound: every script, module worker and stylesheet in assets/ (the map chunk, its shared chunks and the worker
  // all load on the first view), the woff2 files for the UI face weights in use, and the first-view data files.
  const list = ["index.html"];
  for (const a of readdirSync(join(dist, "assets"))) {
    if (/\.(js|mjs|css)$/.test(a) || /^public-sans-latin-(400|600|700)-normal-.*\.woff2$/.test(a)) list.push(`assets/${a}`);
  }
  for (const f of ["points.json", "status.json", "judge_tour.json"]) list.push(`data/${f}`);
  return list.filter((f) => existsSync(join(dist, f)));
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  if (!existsSync(dist)) {
    console.error("check-build: web/dist does not exist; run vite build first");
    process.exit(1);
  }
  const files = walk(dist)
    .filter((p) => TEXT.has(extname(p)))
    .map((p) => [relative(dist, p), readFileSync(p, "utf8")]);
  const problems = checkOrigins(files.map(([f, t]) => [f.startsWith("data/") ? `/data/${f}` : f, t]));
  if (problems.length) {
    console.error("check-build: origin check FAILED (REQ-WEB-PERF.2)");
    for (const p of problems) console.error(`  - ${p}`);
    process.exit(1);
  }
  const copyPath = join(here, "..", "src", "copy", "en.json");
  const reportProblems = reportUrlProblems(JSON.parse(readFileSync(copyPath, "utf8")).links?.report_error_url);
  if (reportProblems.length) {
    console.error("check-build: Report an error link FAILED (REQ-WEB-FRESH.3)");
    for (const p of reportProblems) console.error(`  - ${p}`);
    process.exit(1);
  }
  console.log(`check-build: origin check ok (${files.length} text files, same-origin only)`);

  const view = firstViewFiles();
  let total = 0;
  for (const f of view) total += gz(join(dist, f));
  // basemap tiles are fetched by byte range; the extract's low-zoom tiles are small, counted as header plus 200 KB
  const tiles = existsSync(join(dist, "tiles", "boston.pmtiles")) ? 512 * 1024 : 0;
  total += tiles;
  const mb = (total / 1024 / 1024).toFixed(2);
  const msg = `check-build: first view about ${mb} MB transferred (${view.length} files gzip + ${Math.round(tiles / 1024)} KB tile estimate), budget 3 MB`;
  const verdict = budgetVerdict(total, strict);
  if (verdict.over) {
    console.warn(`${msg}: OVER BUDGET${strict ? "" : " (warning only without --strict)"}`);
    if (verdict.fail) process.exit(1);
  } else console.log(msg);
}
