import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import type { Page, TestInfo } from "@playwright/test";

const shots = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "docs", "screenshots");

/** Save a screenshot for the UX reviewer under docs/screenshots/ (REQ-WEB-TEST.2). */
export async function shot(page: Page, info: TestInfo, name: string): Promise<void> {
  mkdirSync(shots, { recursive: true });
  const motion = info.title.includes("reduced motion on") ? "reduced" : "motion";
  await page.screenshot({ path: join(shots, `${info.project.name}-${motion}-${name}.png`) });
}

/** Press Tab until the focused element's text or label matches, so the test never uses the mouse. */
export async function tabTo(page: Page, name: RegExp | string, max = 80): Promise<void> {
  const re = typeof name === "string" ? new RegExp(`^${name}$`) : name;
  for (let i = 0; i < max; i++) {
    await page.keyboard.press("Tab");
    const label = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null;
      return (el?.getAttribute("aria-label") ?? el?.textContent ?? "").trim();
    });
    if (re.test(label)) return;
  }
  throw new Error(`Tab never reached ${String(name)}`);
}
