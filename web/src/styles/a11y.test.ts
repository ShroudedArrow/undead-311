import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { contrast } from "../lib/contrast";

const css = readFileSync(join(__dirname, "app.css"), "utf8");
const tokens = readFileSync(join(__dirname, "tokens.css"), "utf8");
const hex = (name: string): string => new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})`).exec(tokens)?.[1] as string;
const rules = css.split("}").map((r) => ({ sel: r.split("{")[0].trim(), body: r.split("{")[1] ?? "" }));

describe("contrast floor (REQ-WEB-A11Y.1, design-system.md contrast rules)", () => {
  it("Asphalt text on every light surface meets 4.5:1", () => {
    for (const bg of ["concrete", "crew-white", "canary-copy"]) expect(contrast(hex("asphalt"), hex(bg))).toBeGreaterThanOrEqual(4.5);
  });
  it("Crew white text on Asphalt (header, pressed buttons) meets 4.5:1", () => {
    expect(contrast(hex("crew-white"), hex("asphalt"))).toBeGreaterThanOrEqual(4.5);
  });
  it("pink and orange are never text colors", () => {
    for (const r of rules) expect(r.body, r.sel).not.toMatch(/(^|[;\s])color:\s*var\(--(survey-pink|cone-orange)\)/);
  });
  it("the only text on a pink surface is large bold text with at least 3:1", () => {
    expect(contrast(hex("asphalt"), hex("survey-pink"))).toBeGreaterThanOrEqual(3);
    const stamp = rules.find((r) => r.sel === ".stamp") as { body: string };
    expect(stamp.body).toMatch(/font-size:\s*var\(--step-1\)/);
    expect(stamp.body).toMatch(/font-weight:\s*700/);
    // no other rule puts a pink background behind text
    expect(rules.filter((r) => /background:\s*var\(--survey-pink\)/.test(r.body)).map((r) => r.sel).sort()).toEqual([".autopsy::after", ".stamp-again"]);
  });
  it("orange is never a text surface; the bulk warning keeps Asphalt text on Crew white", () => {
    const orangeBg = rules.filter((r) => /background:\s*var\(--cone-orange\)/.test(r.body));
    expect(orangeBg).toEqual([]);
    const bulk = rules.find((r) => r.sel === ".bulk-warning") as { body: string };
    expect(bulk.body).toMatch(/border-left:[^;]*var\(--cone-orange\)/);
    expect(bulk.body).toMatch(/background:\s*var\(--crew-white\)/);
  });
});

describe("pressed buttons stay readable (REQ-WEB-STREET.1, UX-38)", () => {
  it("the chosen street button is Crew white on Asphalt, not Crew white on Crew white", () => {
    const rule = rules.find((r) => r.sel === '.street-results button[aria-pressed="true"]') as { body: string };
    expect(rule).toBeDefined();
    const bg = /background:\s*var\(--([a-z-]+)\)/.exec(rule.body)?.[1] as string;
    const fg = /(?:^|[;\s])color:\s*var\(--([a-z-]+)\)/.exec(rule.body)?.[1] as string;
    expect(contrast(hex(fg), hex(bg))).toBeGreaterThanOrEqual(4.5);
  });
});

describe("phone header (REQ-WEB-MAP.1, UX-40)", () => {
  it("hides the nav behind the Menu button under 640 px and shows the button only there", () => {
    expect(rules.find((r) => r.sel === ".nav-toggle")?.body).toMatch(/display:\s*none/);
    const phone = css.slice(css.indexOf(".site-nav[data-open=\"false\"]") - 400);
    expect(phone).toMatch(/\.site-nav\[data-open="false"\]\s*\{\s*display:\s*none/);
    expect(css.lastIndexOf("max-width: 640px", css.indexOf('.site-nav[data-open="false"]'))).toBeGreaterThan(css.indexOf(".nav-toggle { display: none"));
  });
});

describe("keyboard and motion (REQ-WEB-A11Y.1)", () => {
  it("has a visible focus style and never removes outlines", () => {
    expect(css).toMatch(/:focus-visible\s*\{[^}]*outline:\s*var\(--focus-ring\)/);
    expect(css).not.toMatch(/outline:\s*(none|0)\b/);
  });
  it("has a skip link and a reduced-motion rule", () => {
    expect(css).toContain(".skip-link");
    expect(css).toMatch(/@media \(prefers-reduced-motion: reduce\)[\s\S]*animation: none/);
  });
  it("gives interactive controls a 44 px minimum height", () => {
    expect(rules.find((r) => r.sel === "button")?.body).toMatch(/min-height:\s*2\.75rem/);
  });
});

/** The body of the first rule whose selector ends with `sel`, searching `css` from `from` on. */
const ruleBody = (sel: string, from = 0): string => {
  const rules = css.slice(from).split("}").map((r) => r.split("{")).filter((p) => p.length >= 2);
  const hit = rules.find((p) => p[p.length - 2].trim() === sel) ?? rules.find((p) => p[p.length - 2].trim().endsWith(sel));
  return hit ? hit[hit.length - 1] : "";
};

describe("the map page fills the screen and nothing moves the map (REQ-WEB-MAP.1, design-system.md map is the hero)", () => {
  it("is exactly one dynamic viewport high, with a floor so a very short window scrolls instead of squeezing the map", () => {
    const body = ruleBody(".shell[data-fit]");
    expect(body).toMatch(/height:\s*100dvh/);
    expect(body).toMatch(/min-height:\s*34rem/);
    expect(ruleBody(".shell[data-fit] .shell-main")).toMatch(/overflow:\s*hidden/);
  });
  it("gives the grid rows a zero minimum so content cannot push the map taller", () => {
    expect(ruleBody(".shell")).toMatch(/minmax\(0,\s*1fr\)/);
    expect(ruleBody(".home")).toMatch(/grid-template-rows:\s*minmax\(0,\s*1fr\)/);
  });
  it("scrolls the sidebar inside itself on wide screens", () => {
    expect(ruleBody(".filters-panel")).toMatch(/overflow-y:\s*auto/);
  });
  it("sizes the map from its frame, not from its own content", () => {
    expect(ruleBody(".map-frame .map-host")).toMatch(/position:\s*absolute/);
    expect(ruleBody(".map-frame .map-host")).toMatch(/inset:\s*0/);
  });
});

describe("phone home: heading hidden visually, count and filters button share a row, filters are a sheet (REQ-WEB-MAP.1, UX-49)", () => {
  const phone = css.indexOf("@media (max-width: 640px) {\n  .home { grid-template-columns");
  it("keeps the h1 for screen readers but out of the layout", () => {
    const body = ruleBody(".filters-panel > h1", phone);
    expect(body).toMatch(/clip-path:\s*inset\(50%\)/);
    expect(body).toMatch(/position:\s*absolute/);
    expect(body).not.toMatch(/display:\s*none/);
  });
  it("puts the count and the Show filters button on one row", () => {
    expect(ruleBody(".filters-panel > .count-block", phone)).toMatch(/grid-column:\s*1/);
    expect(ruleBody(".filters-toggle", phone)).toMatch(/grid-column:\s*2/);
  });
  it("opens the filters as a fixed sheet that is out of the page flow, capped in height, inside the safe area", () => {
    expect(phone).toBeGreaterThan(0);
    const body = ruleBody(".filters-body", phone);
    expect(body).toMatch(/position:\s*fixed/);
    expect(body).toMatch(/max-height:\s*min\(70dvh/);
    expect(body).toMatch(/overflow-y:\s*auto/);
    expect(body).toMatch(/env\(safe-area-inset-bottom\)/);
  });
  it("gives the stage the rest of the first view", () => {
    expect(ruleBody(".home", phone)).toMatch(/grid-template-rows:\s*auto minmax\(0,\s*1fr\)/);
  });
});

describe("methods page layout (REQ-WEB-METHODS.1)", () => {
  it("centres a column of about 70 characters", () => {
    expect(ruleBody(".methods-main")).toMatch(/max-width:\s*var\(--measure\)/);
    expect(ruleBody(".methods-main")).toMatch(/margin-inline:\s*auto/);
    expect(readFileSync(join(__dirname, "tokens.css"), "utf8")).toMatch(/--measure:\s*70ch/);
  });
  it("keeps the contents list in view beside the column only on wide screens", () => {
    const wide = css.indexOf("@media (min-width: 70rem)");
    expect(wide).toBeGreaterThan(0);
    expect(ruleBody(".toc", wide)).toMatch(/position:\s*sticky/);
    expect(ruleBody(".toc", wide)).toMatch(/grid-column:\s*3/);
    expect(ruleBody(".methods-layout")).not.toMatch(/sticky/);
  });
});
