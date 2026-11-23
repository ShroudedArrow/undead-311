import fc from "fast-check";
import { describe, expect, it } from "vitest";
import { decodeShown, PAGE_SIZE, writeShown } from "./paging";

describe("paging state in the URL (REQ-WEB-LINKS.1, design review 6)", () => {
  it("starts at one page and ignores junk", () => {
    expect(decodeShown("")).toBe(PAGE_SIZE);
    expect(decodeShown("n=abc")).toBe(PAGE_SIZE);
    expect(decodeShown("n=-40")).toBe(PAGE_SIZE);
    expect(decodeShown("n=10")).toBe(PAGE_SIZE);
  });
  it("rounds up to whole pages and caps the size", () => {
    expect(decodeShown("n=26")).toBe(50);
    expect(decodeShown("n=75")).toBe(75);
    expect(decodeShown("n=999999")).toBe(5000);
  });
  it("property: the decoded size is a whole number of pages, at least one, and survives a write and a read", () => {
    fc.assert(fc.property(fc.integer({ min: -100, max: 100000 }), (n) => {
      const shown = decodeShown(`n=${n}`);
      expect(shown % PAGE_SIZE).toBe(0);
      expect(shown).toBeGreaterThanOrEqual(PAGE_SIZE);
      expect(decodeShown(writeShown(new URLSearchParams("s=X"), shown))).toBe(shown);
    }));
  });
  it("leaves no n in the address for the first page and keeps other parameters", () => {
    expect(writeShown(new URLSearchParams("s=X&n=50"), PAGE_SIZE).toString()).toBe("s=X");
    expect(writeShown(new URLSearchParams("s=X"), 50).toString()).toBe("s=X&n=50");
  });
});
