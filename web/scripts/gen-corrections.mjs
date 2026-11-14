// REQ-WEB-FRESH.3: render docs/CORRECTIONS.md at build time. Writes src/generated/corrections.json, which the corrections page imports.
// Usage: node scripts/gen-corrections.mjs          (writes the file)
//        node scripts/gen-corrections.mjs --check  (exits 1 if the committed file is stale)
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const source = join(here, "..", "..", "docs", "CORRECTIONS.md");
const target = join(here, "..", "src", "generated", "corrections.json");

/** Parse the corrections log: the heading, the intro lines, and the table rows (Date, What was wrong, Fix). */
export function parseCorrections(md) {
  const lines = md.split(/\r?\n/);
  const title = (lines.find((l) => /^#\s+/.test(l)) ?? "").replace(/^#\s+/, "").trim();
  const intro = [];
  const rows = [];
  let inTable = false;
  for (const raw of lines) {
    const line = raw.trim();
    if (!line || /^#\s+/.test(line)) continue;
    if (line.startsWith("|")) {
      inTable = true;
      const cells = line.replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
      if (cells.every((c) => /^:?-{3,}:?$/.test(c))) continue; // separator row
      if (cells[0].toLowerCase() === "date") continue; // header row
      if (cells.length >= 3 && cells.some(Boolean)) rows.push({ date: cells[0], wrong: cells[1], fix: cells.slice(2).join(" | ") });
    } else if (!inTable) intro.push(line);
  }
  return { title, intro, rows };
}

export function render() {
  return JSON.stringify(parseCorrections(readFileSync(source, "utf8")), null, 2) + "\n";
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const text = render();
  if (process.argv.includes("--check")) {
    if (!existsSync(target) || readFileSync(target, "utf8") !== text) {
      console.error("stale: src/generated/corrections.json (run npm run gen:corrections)");
      process.exit(1);
    }
  } else {
    mkdirSync(dirname(target), { recursive: true });
    writeFileSync(target, text);
    console.log("gen-corrections: wrote src/generated/corrections.json");
  }
}
