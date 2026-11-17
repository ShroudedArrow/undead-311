import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

const dir = join(__dirname, "..", "..", "public", "data");

/** Every zombie of the committed sample export, read from its shards (REQ-EXP-SIZE.3), in file order, as one `zombies` file. */
export function readZombies(): { data_version: string; zombies: { zombie_id: string; tier: string; [k: string]: unknown }[] } {
  const folder = join(dir, "zombies");
  const files = readdirSync(folder).filter((f) => f.endsWith(".json") && f !== "index.json").sort();
  const parts = files.map((f) => JSON.parse(readFileSync(join(folder, f), "utf8")) as { data_version: string; zombies: never[] });
  return { data_version: parts[0]?.data_version ?? "", zombies: parts.flatMap((p) => p.zombies) };
}
