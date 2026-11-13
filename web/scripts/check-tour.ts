// REQ-WEB-JUDGE.2: the judging build (`make build JUDGING=1`) fails unless judge_tour.json is final and every zombie
// in it is in the confirmed validation set. Other builds only validate the shape and print a notice.
import { readFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { checkTour } from "../src/lib/tour.ts";

const dataDir = join(dirname(fileURLToPath(import.meta.url)), "..", "public", "data");
const judging = process.env.JUDGING === "1";
const read = (f: string) => (existsSync(join(dataDir, f)) ? JSON.parse(readFileSync(join(dataDir, f), "utf8")) : null);

const tour = read("judge_tour.json");
if (!tour) {
  console.error("check-tour: public/data/judge_tour.json is missing");
  process.exit(judging ? 1 : 0);
}
const result = checkTour(tour, read("validation.json"), judging);
if (!result.ok) {
  console.error(`check-tour: ${judging ? "JUDGING build refused" : "tour problem"}`);
  for (const e of result.errors) console.error(`  - ${e}`);
  process.exit(1);
}
console.log(`check-tour: ok (${judging ? "judging build" : tour.provisional ? "provisional tour, notice will show" : "final tour"})`);
