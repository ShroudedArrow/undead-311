import fc from "fast-check";
import { describe, expect, it } from "vitest";
import { distanceApartM, formatDistance, splitObjections } from "./autopsy";

describe("splitObjections (REQ-WEB-CARD.1, design review 13)", () => {
  it("splits sentences and keeps street names, colons and numbers whole", () => {
    const notes = "Both cases carry the identical point for the intersection of Foster St & Washington St: an intersection centroid. The re-report came 50 days after the closure; a new fault is plausible. It is 23 m from the original (matched by radius).";
    expect(splitObjections(notes)).toEqual([
      "Both cases carry the identical point for the intersection of Foster St & Washington St: an intersection centroid.",
      "The re-report came 50 days after the closure; a new fault is plausible.",
      "It is 23 m from the original (matched by radius).",
    ]);
  });
  it("returns nothing for an empty or missing note", () => {
    expect(splitObjections("")).toEqual([]);
    expect(splitObjections(null)).toEqual([]);
    expect(splitObjections("   ")).toEqual([]);
  });
  it("property: no text is lost; joining the objections gives the note back with single spaces", () => {
    fc.assert(fc.property(fc.array(fc.stringMatching(/^[A-Z][a-z ]{1,20}\.$/), { maxLength: 6 }), (parts) => {
      const note = parts.join(" ");
      expect(splitObjections(note).join(" ")).toBe(note.replace(/\s+/g, " ").trim());
    }));
  });
});

describe("distance between the two reports (REQ-WEB-CARD.1)", () => {
  it("is symmetric, never negative, and null when a point is missing", () => {
    fc.assert(fc.property(fc.double({ min: 42.2, max: 42.4, noNaN: true }), fc.double({ min: -71.2, max: -70.9, noNaN: true }), fc.double({ min: 42.2, max: 42.4, noNaN: true }), fc.double({ min: -71.2, max: -70.9, noNaN: true }), (a, b, c, d) => {
      const ab = distanceApartM({ lat: a, lon: b }, { lat: c, lon: d }) as number;
      const ba = distanceApartM({ lat: c, lon: d }, { lat: a, lon: b }) as number;
      expect(ab).toBeGreaterThanOrEqual(0);
      expect(ab).toBeCloseTo(ba, 6);
    }));
    expect(distanceApartM({ lat: Number.NaN, lon: 0 }, { lat: 1, lon: 1 })).toBeNull();
  });
  it("writes meters under a kilometer and kilometers above", () => {
    expect(formatDistance(33.4)).toBe("33 m");
    expect(formatDistance(1234)).toBe("1.2 km");
  });
});
