import fc from "fast-check";
import { describe, expect, it } from "vitest";
import index from "../generated/streets.json";
import { haversineM } from "./geo";
import { addFromSamCsv, addFromSamSegments, boundsOf, IndexBuilder, MAX_POINTS, MAX_POINTS_SAM, nearStreet, normalizeStreet, searchStreets, streetsOf, type StreetIndex } from "./streets";

const idx = index as StreetIndex;

describe("street names (REQ-WEB-STREET.1)", () => {
  it("drops house numbers and the word INTERSECTION, and splits cross streets", () => {
    expect(streetsOf("20-22 Radcliffe Rd")).toEqual(["Radcliffe Rd"]);
    expect(streetsOf("INTERSECTION Harcourt St &amp; Saint Botolph St")).toEqual(["Harcourt St", "Saint Botolph St"]);
    expect(streetsOf("1270 Commonwealth Ave")).toEqual(["Commonwealth Ave"]);
    expect(streetsOf(null)).toEqual([]);
    expect(streetsOf("12")).toEqual([]);
  });
  it("matches long and short suffixes and ignores case and punctuation", () => {
    expect(normalizeStreet("Commonwealth Avenue")).toBe(normalizeStreet("COMMONWEALTH AVE."));
    expect(normalizeStreet("Saint Botolph Street")).toBe(normalizeStreet("St. Botolph St"));
  });
  it("property: normalizing twice changes nothing", () => {
    fc.assert(fc.property(fc.string({ maxLength: 30 }), (s) => normalizeStreet(normalizeStreet(s)) === normalizeStreet(s)));
  });
});

describe("street search (REQ-WEB-STREET.1)", () => {
  it("the committed index is sorted, unique by key, and is built from SAM, and has at most MAX_POINTS_SAM points per street", () => {
    expect(idx.source).toBe("sam");
    const keys = idx.streets.map((s) => s.k);
    expect(keys).toEqual([...keys].sort((a, b) => (a < b ? -1 : a > b ? 1 : 0)));
    expect(new Set(keys).size).toBe(keys.length);
    for (const s of idx.streets) {
      expect(s.p.length).toBeGreaterThan(0);
      expect(s.p.length).toBeLessThanOrEqual(MAX_POINTS_SAM);
    }
  });
  it("finds a street by a partial, differently spelled name", () => {
    const r = searchStreets(idx, "commonwealth avenue");
    expect(r[0]?.k).toBe("COMMONWEALTH AVE");
    expect(searchStreets(idx, "commonw")[0]?.k).toBe("COMMONWEALTH AVE");
    expect(searchStreets(idx, "")).toEqual([]);
    expect(searchStreets(idx, "zzzzqqqq")).toEqual([]);
  });
  it("property: searching a street's own name returns it first, and results stay in the index", () => {
    fc.assert(
      fc.property(fc.integer({ min: 0, max: idx.streets.length - 1 }), (i) => {
        const e = idx.streets[i];
        const r = searchStreets(idx, e.n, 8);
        return r.length <= 8 && r.every((x) => idx.streets.includes(x)) && r.some((x) => x.k === e.k);
      }),
      { numRuns: 80 },
    );
  });
});

describe("nearby zombies (REQ-WEB-STREET.1, testing.md property 11)", () => {
  const street = { k: "X ST", n: "X St", p: [[42.35, -71.06], [42.351, -71.06]] as [number, number][] };
  const items = [
    { id: "a", lat: 42.35, lon: -71.0601 },
    { id: "b", lat: 42.3515, lon: -71.06 },
    { id: "c", lat: 42.4, lon: -71.0 },
  ];
  it("lists items within the distance of any point on the street, nearest first", () => {
    const r = nearStreet(street, items, 300);
    expect(r.map((x) => x.item.id)).toEqual(["a", "b"]);
    expect(nearStreet(street, items, 10).map((x) => x.item.id)).toEqual(["a"]);
  });
  it("property: a wider distance never drops an item; distance is symmetric and never negative", () => {
    const coord = fc.record({ lat: fc.double({ min: 42.2, max: 42.4, noNaN: true }), lon: fc.double({ min: -71.2, max: -70.99, noNaN: true }) });
    fc.assert(
      fc.property(fc.array(coord, { maxLength: 15 }), fc.integer({ min: 1, max: 1500 }), fc.integer({ min: 0, max: 1500 }), (cs, r, extra) => {
        const its = cs.map((c, i) => ({ id: String(i), ...c }));
        const narrow = new Set(nearStreet(street, its, r).map((x) => x.item.id));
        const wide = new Set(nearStreet(street, its, r + extra).map((x) => x.item.id));
        return [...narrow].every((id) => wide.has(id));
      }),
    );
    fc.assert(
      fc.property(fc.double({ min: 42, max: 43, noNaN: true }), fc.double({ min: -72, max: -71, noNaN: true }), fc.double({ min: 42, max: 43, noNaN: true }), fc.double({ min: -72, max: -71, noNaN: true }), (a, b, c, d) => {
        const x = haversineM(a, b, c, d);
        return x >= 0 && x === haversineM(c, d, a, b) && haversineM(a, b, a, b) === 0;
      }),
    );
  });
  it("zooms to the box around the street", () => {
    expect(boundsOf(street)).toEqual([-71.06, 42.35, -71.06, 42.351]);
  });
});

describe("SAM address registry input (REQ-WEB-STREET.1)", () => {
  it("reads street, latitude and longitude columns and joins a separate suffix column", () => {
    const b = new IndexBuilder();
    const n = addFromSamCsv(b, 'SAM_ADDRESS_ID,STREET_BODY,STREET_SUFFIX,LATITUDE,LONGITUDE\n1,"Beacon",St,42.3,-71.1\n2,Beacon,St,42.31,-71.11\n3,Arlington St,,42.35,-71.07\n');
    const out = b.build("sam");
    expect(n).toBe(3);
    expect(out.source).toBe("sam");
    expect(out.streets.map((s) => s.k)).toEqual(["ARLINGTON ST", "BEACON ST"]);
    expect(out.streets[1].p).toHaveLength(2);
  });
  it("refuses a file with no street or coordinate columns", () => {
    expect(() => addFromSamCsv(new IndexBuilder(), "a,b\n1,2\n")).toThrow(/street name column/);
  });
  it("keeps at most MAX_POINTS points spread along a long street", () => {
    const b = new IndexBuilder();
    for (let i = 0; i < 100; i++) b.add("Long St", 42.3 + i / 1000, -71.1);
    const e = b.build("sam").streets[0];
    expect(e.p).toHaveLength(MAX_POINTS);
    expect(e.p[0][0]).toBe(42.3);
    expect(e.p[MAX_POINTS - 1][0]).toBe(42.399);
  });
});

describe("SAM street segments input (REQ-WEB-STREET.1, UX-45)", () => {
  const seg = (name: Record<string, string | null>, coords: number[][], type = "LineString") => ({ properties: name, geometry: { type, coordinates: coords } });
  it("names a street from its direction, name, type and suffix, and keeps the first, middle and last vertex of each segment", () => {
    const b = new IndexBuilder();
    const n = addFromSamSegments(b, {
      features: [
        seg({ PRE_DIR: "W", ST_NAME: "BROADWAY", ST_TYPE: null, SUF_DIR: null }, [[-71.05, 42.34], [-71.051, 42.341], [-71.052, 42.342]]),
        seg({ PRE_DIR: null, ST_NAME: "BEACON", ST_TYPE: "ST", SUF_DIR: null }, [[-71.07, 42.35], [-71.071, 42.351]]),
        seg({ PRE_DIR: null, ST_NAME: "BEACON", ST_TYPE: "ST", SUF_DIR: null }, [[-71.08, 42.36], [-71.081, 42.361]]),
      ],
    });
    const out = b.build("sam", MAX_POINTS_SAM);
    expect(n).toBe(3);
    expect(out.streets.map((s) => s.k)).toEqual(["BEACON ST", "W BROADWAY"]);
    expect(out.streets[0].p).toHaveLength(4);
    expect(out.streets[1].p).toHaveLength(3);
  });
  it("skips segments with no street name or no line, and reads MultiLineString", () => {
    const b = new IndexBuilder();
    const n = addFromSamSegments(b, {
      features: [
        seg({ PRE_DIR: null, ST_NAME: null, ST_TYPE: "ST", SUF_DIR: null }, [[-71, 42], [-71.1, 42.1]]),
        seg({ ST_NAME: "A", ST_TYPE: "ST" }, [], "LineString"),
        { properties: { ST_NAME: "ELM", ST_TYPE: "ST" }, geometry: null },
        seg({ ST_NAME: "OAK", ST_TYPE: "ST" }, [[[-71, 42], [-71.1, 42.1]]] as unknown as number[][], "MultiLineString"),
      ],
    });
    expect(n).toBe(1);
    expect(b.build("sam").streets.map((s) => s.k)).toEqual(["OAK ST"]);
  });
  it("keeps every point of a long street up to MAX_POINTS_SAM, so a point lies every few blocks", () => {
    const b = new IndexBuilder();
    for (let i = 0; i < 400; i++) b.add("Long St", 42.3 + i / 10000, -71.1);
    expect(b.build("sam", MAX_POINTS_SAM).streets[0].p).toHaveLength(MAX_POINTS_SAM);
    expect(MAX_POINTS_SAM).toBeGreaterThan(MAX_POINTS);
  });
});
