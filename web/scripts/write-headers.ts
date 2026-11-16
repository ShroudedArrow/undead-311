// REQ-WEB-PERF.3, REQ-OPS-HOST.3: write the host's `_headers` file (the Content Security Policy) into web/dist after the build.
import { writeFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { headersFile } from "../src/lib/csp.ts";

const dist = join(dirname(fileURLToPath(import.meta.url)), "..", "dist");
if (!existsSync(dist)) {
  console.error("write-headers: web/dist does not exist; run vite build first");
  process.exit(1);
}
writeFileSync(join(dist, "_headers"), headersFile());
console.log("write-headers: wrote dist/_headers (same-origin Content Security Policy)");
