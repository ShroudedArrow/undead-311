import { expect, test } from "@playwright/test";
import { shot } from "./helpers";

test.describe("pages for the UX reviewer (REQ-WEB-TEST.2)", () => {
  test("map, filters, table, card and scorecard render and mirror each other", async ({ page }, info) => {
    await page.goto("/");
    await expect(page.getByTestId("map")).toHaveAttribute("data-ready", "true");
    const mapCount = Number(await page.getByTestId("map").getAttribute("data-marker-count"));
    expect(mapCount).toBeGreaterThan(0);
    await expect(page.getByTestId("count")).toContainText(mapCount.toLocaleString("en-US"));
    await shot(page, info, "map");

    await page.getByRole("button", { name: "Table" }).click();
    await expect(page.getByTestId("zombie-table")).toBeVisible();
    await expect(page.locator("[data-testid=zombie-table] tbody tr")).toHaveCount(mapCount);
    await shot(page, info, "table");

    await page.locator("[data-testid=zombie-table] tbody a").first().click();
    await expect(page.getByTestId("autopsy-card")).toBeVisible();
    await shot(page, info, "card");
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("autopsy-card")).toHaveCount(0);

    await page.goto("/scorecard");
    await expect(page.getByText("Closed on time").first()).toBeVisible();
    await shot(page, info, "scorecard");
  });

  test("makes no request to another origin", async ({ page, baseURL }) => {
    const foreign: string[] = [];
    page.on("request", (r) => {
      if (!r.url().startsWith(baseURL as string) && !r.url().startsWith("data:") && !r.url().startsWith("blob:")) foreign.push(r.url());
    });
    await page.goto("/");
    await expect(page.getByTestId("map")).toHaveAttribute("data-ready", "true");
    await page.goto("/judge");
    await page.getByRole("button", { name: "Start the tour" }).click();
    expect(foreign).toEqual([]);
  });

  test("the page runs under the Content Security Policy with no violation (REQ-WEB-PERF.3)", async ({ page }) => {
    const violations: string[] = [];
    page.on("console", (m) => {
      if (/content security policy/i.test(m.text())) violations.push(m.text());
    });
    const res = await page.goto("/");
    expect(res?.headers()["content-security-policy"] ?? "").toContain("default-src 'self'");
    await expect(page.getByTestId("map")).toHaveAttribute("data-ready", "true");
    await page.goto("/?view=table");
    await page.locator("[data-testid=zombie-table] tbody a").first().click();
    await expect(page.getByTestId("autopsy-card")).toBeVisible();
    expect(violations).toEqual([]);
  });

  test("on a phone-sized screen the card is a bottom sheet", async ({ page, viewport }, info) => {
    test.skip((viewport?.width ?? 1000) >= 640, "phone only");
    await page.goto("/?view=table");
    await page.locator("[data-testid=zombie-table] tbody a").first().click();
    const host = page.locator(".card-host");
    await expect(host).toBeVisible();
    const box = await host.boundingBox();
    expect(box?.y ?? 0).toBeGreaterThan(0);
    expect(box?.x ?? 1).toBe(0);
    await shot(page, info, "card-sheet");
  });
});
