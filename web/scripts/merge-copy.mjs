// One-off helper: deep-merge a JSON fragment into src/copy/en.json (keeps key order, adds new keys at the end of each object).
import { readFileSync, writeFileSync } from "node:fs";
const [, , fragment, target = "src/copy/en.json"] = process.argv;
const merge = (a, b) => {
  for (const [k, v] of Object.entries(b)) a[k] = v && typeof v === "object" && !Array.isArray(v) && a[k] && typeof a[k] === "object" ? merge(a[k], v) : v;
  return a;
};
const out = merge(JSON.parse(readFileSync(target, "utf8")), JSON.parse(readFileSync(fragment, "utf8")));
writeFileSync(target, JSON.stringify(out, null, 2) + "\n");
