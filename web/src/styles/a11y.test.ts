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

describe("phone layout: the map comes before the hero text (REQ-WEB-MAP.1, design-system.md map is the hero, UX-12)", () => {
  it("orders the stage ahead of the hero lines under 640 px", () => {
    const phone = css.slice(css.lastIndexOf("UX-12"));
    const order = (sel: string) => Number(new RegExp(`${sel.replace(/[.>\s]/g, (c) => `\\${c}`)}\\s*\\{[^}]*order:\\s*(\\d+)`).exec(phone)?.[1]);
    expect(order(".stage")).toBeLessThan(order(".filters-panel > .hero-text"));
    expect(order(".filters-panel > h1")).toBeLessThan(order(".stage"));
    expect(order(".filters-panel > .filters-toggle")).toBeLessThan(order(".stage"));
  });
});
