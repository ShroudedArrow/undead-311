import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const src = join(__dirname, "..");
function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
}
const PALETTE = ["#cdcbc6", "#2e3134", "#f4f4ef", "#ff3ea5", "#f26b1d", "#efe08a"];

describe("design tokens (REQ-WEB-DESIGN.1)", () => {
  const tokens = readFileSync(join(src, "styles", "tokens.css"), "utf8").toLowerCase();

  it("defines exactly the six palette colors", () => {
    const hexes = [...tokens.matchAll(/#[0-9a-f]{6}\b/g)].map((m) => m[0]);
    expect(hexes.sort()).toEqual([...PALETTE].sort());
  });

  it("no other source file defines a color outside the palette", () => {
    for (const f of walk(src).filter((p) => /\.(css|tsx?)$/.test(p) && !p.endsWith("tokens.css") && !p.includes("generated") && !p.endsWith(".test.ts") && !p.endsWith(".test.tsx"))) {
      const text = readFileSync(f, "utf8").toLowerCase();
      const hexes = [...text.matchAll(/#[0-9a-f]{3,8}\b/g)].map((m) => m[0]).filter((h) => /^#[0-9a-f]{3}$|^#[0-9a-f]{6}$|^#[0-9a-f]{8}$/.test(h));
      for (const h of hexes) expect(PALETTE, `${f} uses ${h}`).toContain(h);
      expect(text, `${f} uses rgb()/hsl()`).not.toMatch(/\b(rgb|rgba|hsl|hsla)\(/);
      expect(text, `${f} uses a gradient`).not.toMatch(/gradient\(/);
    }
  });

  it("names Public Sans for the UI and Courier Prime for forms", () => {
    expect(tokens).toContain('--font-ui: "public sans"');
    expect(tokens).toContain('--font-form: "courier prime"');
  });
});
