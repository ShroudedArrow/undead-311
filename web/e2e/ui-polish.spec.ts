import { expect, test, type Page } from "@playwright/test";

/** The map page fills the screen, opening anything on it never moves the map, and the new controls work (REQ-WEB-MAP.1, REQ-WEB-TIMELAPSE.1, REQ-WEB-METHODS.1). */
const mapBox = async (page: Page) => (await page.getByTestId("map").boundingBox())!;
const openFilters = async (page: Page) => {
  await expect(page.getByTestId("count")).toBeVisible(); // the points have loaded, so the toggle exists where it is shown
  const toggle = page.getByRole("button", { name: /show filters/i });
  if (await toggle.isVisible()) await toggle.click();
};

test("the map page has no page scroll and no sideways scroll", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("map")).toHaveAttribute("data-ready", "true");
  const m = await page.evaluate(() => ({ sh: document.documentElement.scrollHeight, ih: innerHeight, sw: document.documentElement.scrollWidth, iw: innerWidth }));
  expect(m.sh).toBeLessThanOrEqual(m.ih);
  expect(m.sw).toBeLessThanOrEqual(m.iw);
});

test("opening and closing every filter group never moves or resizes the map", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("map")).toHaveAttribute("data-ready", "true");
  await openFilters(page);
  const before = await mapBox(page);
  const groups = page.locator(".filter-group > summary");
  for (let i = 0; i < (await groups.count()); i++) {
    await groups.nth(i).click();
    expect(await mapBox(page)).toEqual(before);
  }
  await page.locator(".filter-group input[type=checkbox]").first().click();
  await expect(page.getByTestId("count")).toContainText("possible zombie");
  expect(await mapBox(page)).toEqual(before);
  const m = await page.evaluate(() => ({ sh: document.documentElement.scrollHeight, ih: innerHeight }));
  expect(m.sh).toBeLessThanOrEqual(m.ih);
});

test("Escape shuts the phone filter sheet and returns focus to its button", async ({ page }, info) => {
  test.skip(info.project.name !== "phone", "the sheet exists under 640 px only");
  await page.goto("/");
  await openFilters(page);
  await expect(page.getByRole("button", { name: /hide filters/i })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: /show filters/i })).toBeFocused();
});

test("the marker key lists the seven case types", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("map")).toHaveAttribute("data-ready", "true");
  const legend = page.getByTestId("map-legend");
  if (!(await legend.evaluate((d) => (d as HTMLDetailsElement).open))) await legend.locator("summary").click(); // open on wide screens, shut on phones
  await expect(legend.locator("li")).toHaveCount(7);
  await expect(legend.getByText("Street fixtures")).toBeVisible();
});

test("methods: a readable column, and the contents list beside it on wide screens only", async ({ page }, info) => {
  await page.goto("/methods");
  const main = page.locator(".methods-main");
  await expect(main).toBeVisible();
  const col = (await main.boundingBox())!;
  const vw = page.viewportSize()!.width;
  expect(col.width).toBeLessThanOrEqual(70 * 16 * 0.62 + 1 + 600); // about 70 characters: never the full width of a wide screen
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const toc = page.getByRole("navigation", { name: "On this page" });
  if (vw >= 1120) {
    const box = (await toc.boundingBox())!;
    expect(box.x).toBeGreaterThan(col.x + col.width);
    await page.evaluate(() => window.scrollTo(0, 2000));
    const after = (await toc.boundingBox())!;
    expect(after.y).toBeGreaterThanOrEqual(0); // sticky: still in view after scrolling
    expect(after.y).toBeLessThan(200);
  } else {
    await expect(toc.locator("details")).toBeVisible();
    expect(info.project.name).toBe("phone");
  }
});

test("time-lapse: focus on a case type and show a trail", async ({ page }) => {
  await page.goto("/timelapse");
  const now = page.getByTestId("timelapse-now");
  await expect(now).toBeVisible();
  const all = (await now.textContent())!;
  await page.getByLabel("Case type").selectOption({ index: 1 });
  await expect(now).not.toHaveText(all);
  await page.getByLabel("Trail").selectOption("3");
  await expect(now).toContainText("in the last 3 months");
  await page.getByLabel("Playback speed").selectOption("4");
  await page.getByRole("button", { name: "Play the time-lapse" }).click();
  await expect(page.getByRole("button", { name: /Pause|Play again/ })).toBeVisible();
});

interface PointsFile { id: string[]; lat: number[]; lon: number[]; tier: string[]; family: string[]; year: number[] }

/** Screen position of every headline marker, in draw order, from the map's own projection, with the ones that sit under a control left out. */
async function markerPixels(page: Page, only?: (i: number, p: PointsFile) => boolean) {
  const res = await page.request.get("/data/points.json");
  const pts = (await res.json()) as PointsFile;
  const map = page.getByTestId("map");
  const box = (await map.boundingBox())!;
  const xy = await map.evaluate(
    (el, p) => (p as { lon: number[]; lat: number[] }).lon.map((lon, i) => (el as unknown as { __project: (a: number, b: number) => { x: number; y: number } }).__project(lon, (p as { lat: number[] }).lat[i])),
    { lon: pts.lon, lat: pts.lat },
  );
  const inView = (x: number, y: number) =>
    x > box.x + 70 && x < box.x + box.width - 90 && y > box.y + 70 && y < box.y + box.height - 70 && !(x < box.x + 300 && y > box.y + box.height - 300);
  return pts.id.map((id, i) => ({ id, i, lon: pts.lon[i], lat: pts.lat[i], x: xy[i].x, y: xy[i].y, ok: pts.tier[i] === "headline" && inView(xy[i].x, xy[i].y), shown: !only || only(i, pts) })).filter((m) => m.shown);
}
/**
 * Open the map filtered to one small group (a case type in one year) whose markers are far apart, so a click on one marker's center cannot
 * be taken by another. Streetlights by default: the stencil L is drawn along the left and bottom of its box, so the middle of that marker is
 * empty paint, which is exactly the spot the old sprite-only picking missed. Tries the smallest groups first; the data decides which one qualifies.
 */
async function openSparseView(page: Page, onlyFamily = "streetlight") {
  const pts = (await (await page.request.get("/data/points.json")).json()) as PointsFile;
  const groups = new Map<string, number>();
  pts.id.forEach((_, i) => groups.set(`${pts.family[i]}|${pts.year[i]}`, (groups.get(`${pts.family[i]}|${pts.year[i]}`) ?? 0) + 1));
  const order = [...groups.entries()].filter(([k, n]) => k.startsWith(`${onlyFamily}|`) && n >= 1 && n <= 12).sort((a, b) => a[1] - b[1] || (a[0] < b[0] ? -1 : 1)).slice(0, 12);
  for (const [key] of order) {
    const [family, year] = key.split("|");
    await page.goto(`/?f=${family}&y=${year}`);
    await expect(page.getByTestId("map")).toHaveAttribute("data-ready", "true");
    await page.waitForTimeout(400);
    const all = await markerPixels(page, (i, p) => p.family[i] === family && String(p.year[i]) === year);
    const ok = all.filter((m) => m.ok);
    const near = (m: (typeof all)[number]) => Math.min(...all.filter((o) => o !== m).map((o) => Math.hypot(o.x - m.x, o.y - m.y)), 1e9);
    const best = ok.map((m) => ({ m, d: near(m) })).sort((a, b) => b.d - a.d)[0];
    if (best && best.d >= 32) return best.m;
  }
  throw new Error("no small group has an isolated marker in view");
}
const idFromUrl = (page: Page) => decodeURIComponent(new URL(page.url()).pathname.replace(/^\/zombie\//, ""));

test("clicking the exact center of a marker opens its card", async ({ page }) => {
  const target = await openSparseView(page);
  await page.mouse.click(target.x, target.y);
  await expect(page.getByTestId("autopsy-card")).toBeVisible();
  expect(idFromUrl(page)).toBe(target.id);
});

test("clicking a marker's center and a few pixels from it opens the same card, so the middle is not a dead spot", async ({ page }, info) => {
  const target = await openSparseView(page);
  const offsets = info.project.name === "phone" ? [[0, 0], [5, 0], [0, -9]] : [[0, 0], [4, 0], [0, 7]];
  for (const [dx, dy] of offsets) {
    // selecting a marker eases the map onto it, so find where the marker is now (the ease takes 600 ms, or none under reduced motion)
    await page.waitForTimeout(900);
    const now = await page.getByTestId("map").evaluate((el, p) => (el as unknown as { __project: (a: number, b: number) => { x: number; y: number } }).__project(p.lon, p.lat), { lon: target.lon, lat: target.lat });
    await page.mouse.click(now.x + dx, now.y + dy);
    await expect(page.getByTestId("autopsy-card")).toBeVisible();
    expect(idFromUrl(page)).toBe(target.id);
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("autopsy-card")).toHaveCount(0);
  }
});

test("where two markers overlap, clicking the center of the one drawn on top opens that one", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("map")).toHaveAttribute("data-ready", "true");
  await page.waitForTimeout(500);
  const all = await markerPixels(page);
  const shown = all.filter((m) => m.ok);
  // j was drawn after i and sits within 9 px of it; nothing drawn after j is near j, so j is visibly on top at its own center
  const pair = shown
    .map((j) => ({ j, i: shown.find((i) => i.i < j.i && Math.hypot(i.x - j.x, i.y - j.y) <= 9) }))
    .find((p) => p.i && all.every((o) => o.i <= p.j.i || Math.hypot(o.x - p.j.x, o.y - p.j.y) > 40));
  test.skip(!pair, "no overlapping pair in this view of the data");
  await page.mouse.click(pair!.j.x, pair!.j.y);
  await expect(page.getByTestId("autopsy-card")).toBeVisible();
  expect(idFromUrl(page)).toBe(pair!.j.id);
});

test("the table still selects a marker's card by keyboard", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("count")).toBeVisible();
  await page.getByRole("button", { name: "Table" }).click();
  const first = page.locator("[data-testid=zombie-table] tbody a").first();
  await first.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("autopsy-card")).toBeVisible();
});

test("on a phone a tap just outside the painted circle still hits, because the target is 44 px across", async ({ page }, info) => {
  test.skip(info.project.name !== "phone", "the 44 px target is for phones");
  const target = await openSparseView(page);
  // the painted circle is 26 px across (13 px radius); 18 px from the center is outside it and inside the 22 px target
  await page.mouse.click(target.x, target.y + 18);
  await expect(page.getByTestId("autopsy-card")).toBeVisible();
  expect(idFromUrl(page)).toBe(target.id);
});

for (const width of [320, 360, 390]) {
  test(`no page scrolls sideways at ${width} px wide`, async ({ page }) => {
    await page.setViewportSize({ width, height: 740 });
    for (const path of ["/", "/methods", "/timelapse", "/scorecard", "/durability", "/street", "/repeat"]) {
      await page.goto(path);
      await page.waitForTimeout(600);
      const over = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
      expect(over, `${path} at ${width}px`).toBeLessThanOrEqual(0);
    }
  });
}

test("the phone filter sheet leaves no half-cut Map and Table buttons showing", async ({ page }, info) => {
  test.skip(info.project.name !== "phone", "the sheet exists under 640 px only");
  await page.goto("/");
  await openFilters(page);
  await expect(page.locator(".view-switch")).toHaveCSS("visibility", "hidden");
  await page.keyboard.press("Escape");
  await expect(page.locator(".view-switch")).toHaveCSS("visibility", "visible");
});
