import { expect, test } from "@playwright/test";

/**
 * UX-52 (issue 192), REQ-WEB-MAP.1: on small phones the count heading and Show filters share a row and the map still
 * starts high on the page. Measured at 390 (unchanged), 360 and 320 px wide.
 */
const SIZES = [
  { w: 390, h: 844, maxTop: 330 },
  { w: 360, h: 640, maxTop: 300 },
  { w: 320, h: 568, maxTop: 300 },
];

for (const s of SIZES) {
  test(`phone ${s.w}px: the map starts within ${s.maxTop}px and Show filters sits beside the count`, async ({ page }) => {
    await page.setViewportSize({ width: s.w, height: s.h });
    await page.goto("/");
    const count = page.getByTestId("count");
    await expect(count).toBeVisible();
    const toggle = page.getByRole("button", { name: /show filters/i });
    const cb = (await count.boundingBox())!;
    const tb = (await toggle.boundingBox())!;
    // same row: the vertical ranges overlap
    expect(tb.y).toBeLessThan(cb.y + cb.height);
    expect(cb.y).toBeLessThan(tb.y + tb.height);
    const map = (await page.getByTestId("map").boundingBox())!;
    console.log(`${s.w}px map top ${Math.round(map.y)}`);
    expect(map.y).toBeLessThan(s.maxTop);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
    expect(overflow).toBe(false);
  });
}
