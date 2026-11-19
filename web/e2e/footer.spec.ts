import { expect, test } from "@playwright/test";
import { shot } from "./helpers";

/** REQ-WEB-DESIGN.3: the independence bar collapses to a one-line note, gives the map its room, reopens, and stays full on the methods page. */
const FULL = "Independent project. Not affiliated with the City of Boston.";
const NOTE = "Independent project, not affiliated with the City of Boston";

test("closing the bar gives its height to the map, leaves a one-line note, and the choice survives a reload", async ({ page }, info) => {
  await page.goto("/");
  const map = page.getByTestId("map");
  await expect(map).toHaveAttribute("data-ready", "true");
  const before = (await map.boundingBox())!;
  const bar = (await page.locator(".site-footer").boundingBox())!;
  await page.getByRole("button", { name: "Hide the notice bar" }).click();
  const note = page.getByRole("button", { name: NOTE });
  await expect(note).toBeVisible();
  await expect(note).toBeFocused();
  await expect(page.getByText(FULL)).toHaveCount(0);
  const after = (await map.boundingBox())!;
  // the map gets (almost all of) the bar's height; on a wide screen the note floats over the sidebar, on a phone over the map's corner
  expect(after.height).toBeGreaterThanOrEqual(before.height + bar.height - 2);
  const n = (await note.boundingBox())!;
  expect(n.height).toBeLessThanOrEqual(52); // a 44 px target, the text in at most two short lines
  expect(n.height).toBeGreaterThanOrEqual(44);
  // still no page scroll on the map page
  const m = await page.evaluate(() => ({ sh: document.documentElement.scrollHeight, ih: innerHeight }));
  expect(m.sh).toBeLessThanOrEqual(m.ih);
  // the note does not sit on the map credit or the marker key button
  const overlaps = (a: { x: number; y: number; width: number; height: number }, b: typeof a) => a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;
  expect(overlaps(n, (await page.locator(".maplibregl-ctrl-attrib").boundingBox())!)).toBe(false);
  expect(overlaps(n, (await page.locator(".map-legend summary").boundingBox())!)).toBe(false);
  await shot(page, info, "footer-collapsed");
  await page.reload();
  await expect(page.getByRole("button", { name: NOTE })).toBeVisible();
  await expect(page.getByText(FULL)).toHaveCount(0);
  // reopening brings back the whole bar with the licenses, and puts focus on its close button
  await page.getByRole("button", { name: NOTE }).click();
  await expect(page.getByText(FULL)).toBeVisible();
  await expect(page.locator(".site-footer")).toContainText("ODC-PDDL");
  await expect(page.getByRole("button", { name: "Hide the notice bar" })).toBeFocused();
  await page.reload();
  await expect(page.getByText(FULL)).toBeVisible();
});

test("the methods page always shows the full notice and the license credits, even after the bar was closed", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Hide the notice bar" }).click();
  await page.goto("/methods");
  await expect(page.getByText(FULL)).toBeVisible();
  await expect(page.locator(".site-footer")).toContainText("SIL Open Font License");
  await expect(page.getByRole("button", { name: "Hide the notice bar" })).toHaveCount(0);
});

test("the bar still closes and reopens when storage is blocked", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(window, "localStorage", { get() { throw new Error("blocked"); } });
  });
  await page.goto("/scorecard");
  await page.getByRole("button", { name: "Hide the notice bar" }).click();
  await page.getByRole("button", { name: NOTE }).click();
  await expect(page.getByText(FULL)).toBeVisible();
});
