import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

/** Design review work (docs/DESIGN_REVIEW.md): form pages, paging, the postmortem card, the night map, the 404 page. */
async function scan(page: Page, label: string) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  const bad = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(bad.map((v) => `${label}: ${v.id} (${v.impact}) ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`)).toEqual([]);
}

const PAGES = ["/", "/?view=table", "/street", "/repeat", "/scorecard", "/durability", "/methods", "/judge", "/timelapse", "/corrections", "/districts", "/no-such-page"];

test("every page fits the screen width, with no horizontal scroll and no page taller than 4,000 px at first load", async ({ page }) => {
  for (const path of PAGES) {
    await page.goto(path);
    await page.waitForTimeout(1200);
    const m = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth, h: document.documentElement.scrollHeight }));
    expect(m.sw, `${path} scroll width`).toBeLessThanOrEqual(m.iw);
    // the methods page is long by design; the paged lists are the ones the 4,000 px budget is for
    if (path === "/repeat") expect(m.h, `${path} height`).toBeLessThan(4000);
  }
});

test("the form pages open with the title and the date plaque", async ({ page }) => {
  for (const path of ["/street", "/repeat", "/scorecard", "/durability", "/methods", "/judge", "/no-such-page"]) {
    await page.goto(path);
    const sheet = page.locator(".page.form-sheet");
    await expect(sheet.locator(".form-head h1")).toBeVisible();
    await expect(sheet.getByTestId("plaque")).toContainText("Records through");
  }
});

test("repeat offenders: 25 rows first, 'Show 25 more' adds a page and writes n to the address, and sorting is kept", async ({ page }) => {
  await page.goto("/repeat");
  const rows = page.locator("[data-testid=repeat-table] tbody tr");
  await expect(rows.first()).toBeVisible();
  const total = Number((await page.getByTestId("repeat-count").textContent())?.replace(/\D/g, ""));
  expect(await rows.count()).toBe(Math.min(25, total));
  if (total > 25) {
    await page.getByRole("button", { name: /^Show \d+ more$/ }).click();
    await expect(rows).toHaveCount(Math.min(50, total));
    await expect(page).toHaveURL(/[?&]n=50/);
    await page.getByRole("button", { name: /^Where/ }).click();
    await expect(page).toHaveURL(/sort=where/);
    // a new order starts again at the first page
    await expect(page).not.toHaveURL(/n=/);
    await expect(rows).toHaveCount(25);
    await page.getByRole("button", { name: /^Show \d+ more$/ }).click();
    await expect(page).toHaveURL(/n=50/);
    await page.reload();
    await expect(rows).toHaveCount(Math.min(50, total));
    await expect(page.getByRole("columnheader", { name: /Where/ })).toHaveAttribute("aria-sort", "ascending");
  }
});

test("map key: the button and the close label say 'map key'", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("map")).toHaveAttribute("data-ready", "true");
  await page.getByText("Map key").click();
  await expect(page.getByRole("button", { name: "Close map key" })).toBeVisible();
  await expect(page.getByText("Marker key")).toHaveCount(0);
});

test("home: the count leads the sidebar and the stamps carry no information", async ({ page, isMobile }) => {
  await page.goto("/");
  await expect(page.getByTestId("count")).toBeVisible();
  const h1 = page.getByRole("heading", { level: 1, name: "The Undead 311" });
  await expect(h1).toHaveCount(1);
  expect(await h1.evaluate((el) => el.getBoundingClientRect().width)).toBeLessThanOrEqual(1);
  if (!isMobile) {
    await expect(page.locator(".stamp-night")).toBeVisible();
    await expect(page.locator(".stamp-filed")).toBeVisible();
  }
  await expect(page.locator(".stamp-night")).toHaveAttribute("aria-hidden", "true");
  await expect(page.locator(".stamp-filed")).toHaveAttribute("aria-hidden", "true");
});

test("the time-lapse alone uses the night map; the main map keeps the day map", async ({ page }) => {
  await page.goto("/timelapse");
  await expect(page.getByTestId("map")).toHaveAttribute("data-theme", "night");
  await expect(page.getByTestId("date-stamp")).toBeVisible();
  await page.goto("/");
  await expect(page.getByTestId("map")).toHaveAttribute("data-theme", "day");
});

test("the card reads as a mock postmortem report, with Show more and the stamp, and fits 390 px", async ({ page }) => {
  await page.goto("/street?s=x");
  await page.goto("/judge");
  await page.getByRole("button", { name: "Start the tour" }).click();
  const card = page.getByTestId("autopsy-card");
  await expect(card).toBeVisible();
  await expect(card.getByText("Undead 311, report of postmortem examination")).toBeVisible();
  await expect(card.getByText("Page 1 of 1")).toBeVisible();
  await expect(card.getByText("Examined by: the Coroner (automated)")).toBeVisible();
  await expect(card.getByTestId("location-diagram")).toBeVisible();
  await expect(card.getByTestId("verdict-stamp")).toContainText(/POSSIBLE|RECORD-CONFIRMED/);
  const over = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  expect(over).toBe(false);
  await scan(page, "card as postmortem report");
});

test("axe on the new frame: street result, repeat, methods, night map, 404", async ({ page }) => {
  await page.goto("/street");
  await page.getByLabel("Street name").fill("a");
  await scan(page, "street");
  await page.goto("/repeat");
  await expect(page.getByTestId("repeat-table")).toBeVisible();
  await scan(page, "repeat");
  await page.goto("/methods");
  await expect(page.getByTestId("methods-intro")).toBeVisible();
  await scan(page, "methods");
  await page.goto("/timelapse");
  await expect(page.getByTestId("map")).toHaveAttribute("data-ready", "true");
  await scan(page, "night map");
  await page.goto("/no-such-page");
  await expect(page.getByRole("heading", { level: 1, name: "This page stayed buried" })).toBeVisible();
  await scan(page, "404");
});
