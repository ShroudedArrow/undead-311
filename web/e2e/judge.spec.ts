import { expect, test } from "@playwright/test";
import { shot, tabTo } from "./helpers";

/** REQ-WEB-TEST.2, REQ-WEB-JUDGE.1, .4: the judge-mode path, keyboard only, with reduced motion on and off. */
for (const reduced of [false, true]) {
  test.describe(`judge mode, reduced motion ${reduced ? "on" : "off"}`, () => {
    test.use({ reducedMotion: reduced ? "reduce" : "no-preference" });

    test(`keyboard only: open, start, see three cards, reach the map (reduced motion ${reduced ? "on" : "off"})`, async ({ page }, info) => {
      await page.goto("/");
      await expect(page.getByTestId("map")).toBeVisible();

      // From the first screen: the entry link is reachable by Tab.
      await tabTo(page, "Start the 60-second tour");
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(/\/judge$/);
      await expect(page.getByTestId("provisional-notice")).toBeVisible();
      await shot(page, info, "judge-intro");

      await tabTo(page, "Start the tour");
      await page.keyboard.press("Enter");

      for (const n of [1, 2, 3]) {
        await expect(page.getByRole("heading", { name: `Zombie ${n} of 3` })).toBeVisible();
        await expect(page.getByTestId("autopsy-card")).toBeVisible();
        await expect(page.getByText("Cause of death")).toBeVisible();
        await shot(page, info, `judge-step-${n}`);
        await page.keyboard.press("ArrowRight");
      }

      await expect(page.getByTestId("tour-done")).toBeVisible();
      await shot(page, info, "judge-done");
      await tabTo(page, "Open the map");
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(/\/$/);
      await expect(page.getByTestId("map")).toHaveAttribute("data-ready", "true");
      await expect(page.getByTestId("map")).not.toHaveAttribute("data-marker-count", "0");
      await shot(page, info, "map");
    });

    test(`escape skips the tour (reduced motion ${reduced ? "on" : "off"})`, async ({ page }) => {
      await page.goto("/judge");
      await tabTo(page, "Start the tour");
      await page.keyboard.press("Enter");
      await expect(page.getByTestId("tour-step")).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(page).toHaveURL(/\/$/);
    });
  });
}

test.describe("judge mode timing", () => {
  test.use({ reducedMotion: "no-preference" });
  test("advances by itself about every 20 seconds and can be paused", async ({ page }) => {
    await page.clock.install();
    await page.goto("/judge");
    await page.getByRole("button", { name: "Start the tour" }).click();
    await expect(page.getByTestId("tour-step")).toHaveAttribute("data-step", "0");
    await page.clock.runFor(21_000);
    await expect(page.getByTestId("tour-step")).toHaveAttribute("data-step", "1");
    await page.getByRole("button", { name: "Pause" }).click();
    await page.clock.runFor(40_000);
    await expect(page.getByTestId("tour-step")).toHaveAttribute("data-step", "1");
    await page.getByRole("button", { name: "Resume" }).click();
    await page.clock.runFor(61_000);
    await expect(page.getByTestId("tour-done")).toBeVisible();
  });
});

test.describe("reduced motion", () => {
  test.use({ reducedMotion: "reduce" });
  test("the tour does not advance by itself", async ({ page }) => {
    await page.clock.install();
    await page.goto("/judge");
    await page.getByRole("button", { name: "Start the tour" }).click();
    await page.clock.runFor(70_000);
    await expect(page.getByTestId("tour-step")).toHaveAttribute("data-step", "0");
  });
});
