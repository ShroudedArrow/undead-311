import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

/** REQ-WEB-A11Y.2: axe scan of judge mode (and the other pages) with no serious or critical violations. */
async function scan(page: Page, label: string) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  const bad = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(bad.map((v) => `${label}: ${v.id} (${v.impact}) ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`)).toEqual([]);
}

for (const reduced of [false, true]) {
  test.describe(`axe, reduced motion ${reduced ? "on" : "off"}`, () => {
    test.use({ reducedMotion: reduced ? "reduce" : "no-preference" });

    test("judge mode: intro, each step and the end", async ({ page }) => {
      await page.goto("/judge");
      await expect(page.getByRole("button", { name: "Start the tour" })).toBeEnabled();
      await scan(page, "judge intro");
      await page.getByRole("button", { name: "Start the tour" }).click();
      for (const n of [1, 2, 3]) {
        await expect(page.getByRole("heading", { name: `Zombie ${n} of 3` })).toBeVisible();
        await scan(page, `judge step ${n}`);
        await page.keyboard.press("ArrowRight");
      }
      await expect(page.getByTestId("tour-done")).toBeVisible();
      await scan(page, "judge done");
    });
  });
}

test("map page, table view, card and scorecard", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("map")).toHaveAttribute("data-ready", "true");
  await scan(page, "map");
  await page.getByRole("button", { name: "Table" }).click();
  await expect(page.getByTestId("zombie-table")).toBeVisible();
  await scan(page, "table");
  await page.locator("[data-testid=zombie-table] tbody a").first().click();
  await expect(page.getByTestId("autopsy-card")).toBeVisible();
  await scan(page, "card");
  await page.goto("/scorecard");
  await expect(page.getByText("Closed on time").first()).toBeVisible();
  await scan(page, "scorecard");
});

test("durability page: survival chart, funnel, leaderboard (REQ-WEB-CHARTS, REQ-WEB-A11Y.2)", async ({ page }) => {
  await page.goto("/durability");
  await expect(page.getByTestId("survival-chart")).toBeVisible();
  await expect(page.getByTestId("leaderboard")).toBeVisible();
  await scan(page, "durability");
});

test("chart text is at least 12 CSS px on every screen (REQ-WEB-CHARTS.1, REQ-WEB-A11Y.1; UX-19)", async ({ page }) => {
  await page.goto("/durability");
  for (const id of ["survival-chart", "funnel-chart"]) {
    await expect(page.getByTestId(id)).toBeVisible();
    const sizes = await page.getByTestId(id).locator("text.chart-tick, text.chart-axis").evaluateAll((nodes) =>
      nodes.map((n) => {
        const svg = n.ownerSVGElement as SVGSVGElement;
        const scale = svg.getBoundingClientRect().width / svg.viewBox.baseVal.width;
        return parseFloat(getComputedStyle(n).fontSize) * scale;
      }),
    );
    expect(sizes.length).toBeGreaterThan(0);
    for (const px of sizes) expect(px, id).toBeGreaterThanOrEqual(11.9);
  }
});

test("methods and corrections pages (REQ-WEB-METHODS.1, REQ-WEB-FRESH.3, REQ-WEB-A11Y.2)", async ({ page }) => {
  await page.goto("/methods");
  await expect(page.getByTestId("excess-table")).toBeVisible();
  await expect(page.getByTestId("nightly-status")).toBeVisible();
  await expect(page.getByTestId("leaves-out")).toBeVisible();
  await scan(page, "methods");
  await page.goto("/corrections");
  await expect(page.getByRole("heading", { name: "Corrections log" })).toBeVisible();
  await scan(page, "corrections");
});
