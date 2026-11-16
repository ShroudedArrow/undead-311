import fc from "fast-check";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { gapWords, neighborhoodImagePath, neighborhoodShareHtml, neighborhoodSummaries, shareSlug, stubHtml, zombieImagePath, zombieShareHtml, type GapText, type ShareText } from "./share";
import { formatGap } from "./format";
import { DEFAULT_STREET_STATE, decodeStreetState, encodeStreetState, STREET_RADII_M, type StreetState } from "./url";
import en from "../copy/en.json";

describe("Property W7: URL state round-trips (REQ-WEB-LINKS.1)", () => {
  it("the street page state survives encode then decode", () => {
    const arb: fc.Arbitrary<StreetState> = fc.record({ key: fc.option(fc.string({ minLength: 1, maxLength: 20 }), { nil: null }), radius: fc.constantFrom(...STREET_RADII_M) });
    fc.assert(fc.property(arb, (s) => {
      const back = decodeStreetState(encodeStreetState(s));
      // a state with no street carries no distance, so only the street is compared then
      return s.key === null ? back.key === null : back.key === s.key && back.radius === s.radius;
    }));
  });
  it("the default street state is an empty query; junk distances fall back to the default", () => {
    expect(encodeStreetState(DEFAULT_STREET_STATE)).toBe("");
    expect(decodeStreetState("s=A&r=7").radius).toBe(150);
    expect(decodeStreetState("s=A&r=300")).toEqual({ key: "A", radius: 300 });
  });
});

describe("share file names and templates (REQ-WEB-LINKS.2)", () => {
  const text: ShareText = { ...en.share, stamp_closed: en.card.stamp_closed, stamp_again: en.card.stamp_again };
  it("slugs are file-name safe and stable, and distinct zombie IDs keep distinct paths", () => {
    expect(zombieImagePath("101001245457:101001323306")).toBe("share/zombie/101001245457-101001323306.png");
    expect(neighborhoodImagePath("Allston / Brighton")).toBe("share/neighborhood/allston-brighton.png");
    fc.assert(fc.property(fc.string(), (s) => /^[a-z0-9]+(-[a-z0-9]+)*$/.test(shareSlug(s)) && shareSlug(shareSlug(s)) === shareSlug(s)));
  });
  it("the zombie image says possible zombie, names the place and the gap, and escapes markup", () => {
    const html = zombieShareHtml({ familyLabel: "Signs", neighborhood: "<b>Back Bay</b>", gap: "3 days" }, text);
    expect(html).toContain("Possible zombie");
    expect(html).toContain("Signs in &lt;b&gt;Back Bay&lt;/b&gt;");
    expect(html).toContain("3 days later");
    expect(html).toContain("Not affiliated with the City of Boston");
    expect(html).not.toMatch(/letter-spacing|text-transform/);
  });
  it("the neighborhood image carries the count and the floor note", () => {
    const html = neighborhoodShareHtml({ neighborhood: "Roxbury", count: 12, topFamilyLabel: "Signs", topFamilyCount: 5 }, text);
    expect(html).toContain("12 Boston 311 cases");
    expect(html).toContain("is a floor");
    expect(html).toContain("Signs (5)");
  });
  it("summaries count headline zombies only, most first", () => {
    const z = (neighborhood: string | null, type_family: string, tier = "headline") => ({ neighborhood, type_family, tier });
    const out = neighborhoodSummaries([z("A", "sign"), z("B", "sign"), z("B", "sidewalk"), z("B", "sign"), z("C", "sign", "city_rereport"), z(null, "sign")], (f) => f.toUpperCase());
    expect(out.map((o) => [o.neighborhood, o.count, o.topFamilyLabel])).toEqual([["B", 3, "SIGN"], ["A", 1, "SIGN"]]);
  });
  it("the crawler stub names the image and redirects without script", () => {
    const html = stubHtml({ title: "T", description: "D", imageUrl: "/share/x.png", target: "/zombie/1" });
    expect(html).toContain('og:image" content="/share/x.png"');
    expect(html).toContain('http-equiv="refresh"');
    expect(html).not.toContain("<script");
  });
  it("property: the build script words a gap exactly as the card does", () => {
    fc.assert(fc.property(fc.double({ min: 0, max: 400, noNaN: true }), (d) => gapWords(d, en.card as GapText) === formatGap(d)));
  });
  it("draws the spray-circle marker, not a CSS circle, on both share pages (REQ-WEB-LINKS.2, UX-44)", () => {
    const z = zombieShareHtml({ familyLabel: "Pothole", neighborhood: "Dorchester", gap: "3 days" }, text);
    const n = neighborhoodShareHtml({ neighborhood: "Dorchester", count: 4, topFamilyLabel: null, topFamilyCount: 0 }, text);
    for (const html of [z, n]) {
      expect(html).toContain('<img class="circle" alt="" src="data:image/svg+xml;base64,');
      expect(html).not.toContain("border-radius:50%");
      expect(html).not.toMatch(/https?:\/\/(?!www\.w3\.org)/);
    }
  });
  it("the committed template files are in sync with en.json share keys", () => {
    const src = readFileSync(join(__dirname, "..", "..", "scripts", "make-share-images.ts"), "utf8");
    for (const k of ["zombie_where", "zombie_line", "neighborhood_line", "unknown_neighborhood"]) expect(Object.keys(en.share)).toContain(k);
    expect(src).toContain("zombieShareHtml");
  });
});
