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

test("axis titles never overlap tick labels (REQ-WEB-CHARTS.1, REQ-WEB-A11Y.1; UX-27)", async ({ page }) => {
  await page.goto("/durability");
  for (const id of ["survival-chart", "funnel-chart"]) {
    await expect(page.getByTestId(id)).toBeVisible();
    const boxes = await page.getByTestId(id).evaluate((svg) => {
      const rect = (n: Element) => { const r = n.getBoundingClientRect(); return { l: r.left, r: r.right, t: r.top, b: r.bottom }; };
      return {
        titles: [...svg.querySelectorAll("text.chart-axis")].map(rect),
        ticks: [...svg.querySelectorAll("text.chart-tick")].map(rect),
      };
    });
    expect(boxes.titles.length).toBeGreaterThan(0);
    for (const a of boxes.titles) for (const b of boxes.ticks) {
      const overlap = a.l < b.r && b.l < a.r && a.t < b.b && b.t < a.b;
      expect(overlap, `${id} axis title overlaps a tick label`).toBe(false);
    }
    // UX-58: tick labels never touch each other either
    for (let i = 0; i < boxes.ticks.length; i++) for (let j = i + 1; j < boxes.ticks.length; j++) {
      const a = boxes.ticks[i], b = boxes.ticks[j];
      const overlap = a.l < b.r && b.l < a.r && a.t < b.b && b.t < a.b;
      expect(overlap, `${id} tick labels ${i} and ${j} touch`).toBe(false);
    }
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

test("delight pages: street, repeat offenders, time-lapse, districts, methods sliders (REQ-WEB-A11Y.2)", async ({ page }) => {
  await page.goto("/street");
  await page.getByLabel("Street name").fill("commonwealth");
  await page.getByRole("button", { name: "Commonwealth Ave" }).click();
  await expect(page.getByTestId("street-result")).toBeVisible();
  await scan(page, "street");
  await page.goto("/repeat");
  await expect(page.getByTestId("repeat-table")).toBeVisible();
  await scan(page, "repeat offenders");
  await page.goto("/timelapse");
  await expect(page.getByTestId("timelapse-now")).toBeVisible();
  await scan(page, "time-lapse");
  await page.goto("/districts");
  await scan(page, "districts");
  await page.goto("/methods");
  await expect(page.getByTestId("sliders")).toBeVisible();
  await scan(page, "methods with sliders and open data");
  await page.goto("/scorecard");
  await expect(page.getByTestId("score-excess").first()).toBeVisible();
  await scan(page, "scorecard with excess");
});

test("the map page has one labeled map stop and the site focus style on its controls (UX-56, UX-57, REQ-WEB-A11Y.1)", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("map")).toHaveAttribute("data-ready", "true");
  const overlay = page.locator("canvas#deckgl-overlay");
  await expect(overlay).toHaveAttribute("tabindex", "-1");
  await expect(overlay).toHaveAttribute("aria-hidden", "true");
  // every focusable element on the page has an accessible name
  const unnamed = await page.evaluate(() => {
    const focusable = [...document.querySelectorAll<HTMLElement>("a[href], button, input, select, textarea, canvas, [tabindex]")]
      .filter((e) => e.tabIndex >= 0 && !e.closest("[hidden], [aria-hidden='true']") && getComputedStyle(e).visibility !== "hidden");
    return focusable.filter((e) => !(e.getAttribute("aria-label") || e.getAttribute("aria-labelledby") || e.getAttribute("title") || (e.textContent ?? "").trim() || (e as HTMLInputElement).labels?.length)).map((e) => e.outerHTML.slice(0, 80));
  });
  expect(unnamed).toEqual([]);
  // MapLibre's blue glow is replaced by the Asphalt outline
  const zoom = page.getByRole("button", { name: /zoom in/i });
  await zoom.focus();
  await page.keyboard.press("Shift+Tab");
  await page.keyboard.press("Tab");
  const style = await zoom.evaluate((b) => { const c = getComputedStyle(b); return { shadow: c.boxShadow, outline: c.outlineStyle, width: c.outlineWidth }; });
  expect(style.shadow).toBe("none");
  expect(style.outline).toBe("solid");
  expect(style.width).toBe("3px");
});
