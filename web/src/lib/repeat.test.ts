import fc from "fast-check";
import { describe, expect, it } from "vitest";
import type { Zombie } from "./parse";
import { chainRows, firstZombieOfChain, REPEAT_MIN_HEADLINE, sortChains, type Chain } from "./repeat";

const chain = (over: Partial<Chain> = {}): Chain => ({ chain_id: "c1", times_risen: 3, headline_count: 3, incident_ids: ["i1"], lat: 42.3, lon: -71.1, block_level: false, type_family: "sign", neighborhood: "Back Bay", ...over });
const arb = fc.record({
  chain_id: fc.string({ minLength: 1, maxLength: 6 }),
  times_risen: fc.integer({ min: 1, max: 20 }),
  headline_count: fc.integer({ min: 0, max: 20 }),
  incident_ids: fc.constant(["i"]),
  block_level: fc.boolean(),
}) as fc.Arbitrary<Chain>;

describe("repeat offenders (REQ-WEB-REPEAT.1)", () => {
  it("shows only chains with at least 3 headline zombies, even if times_risen is higher", () => {
    const out = sortChains([chain({ chain_id: "a", times_risen: 9, headline_count: 2 }), chain({ chain_id: "b", times_risen: 4, headline_count: 3 })]);
    expect(out.map((c) => c.chain_id)).toEqual(["b"]);
  });
  it("orders by returns, then headline count, then ID", () => {
    const out = sortChains([chain({ chain_id: "b", times_risen: 4 }), chain({ chain_id: "a", times_risen: 4 }), chain({ chain_id: "c", times_risen: 6 }), chain({ chain_id: "d", times_risen: 4, headline_count: 5 })]);
    expect(out.map((c) => c.chain_id)).toEqual(["c", "d", "a", "b"]);
  });
  it("property: output is sorted, a subset of the input, every chain meets the minimum, and input order does not matter", () => {
    fc.assert(
      fc.property(fc.array(arb, { maxLength: 25 }), (cs) => {
        const out = sortChains(cs);
        const rev = sortChains([...cs].reverse());
        const sorted = out.every((c, i) => i === 0 || out[i - 1].times_risen >= c.times_risen);
        return sorted && out.every((c) => c.headline_count >= REPEAT_MIN_HEADLINE && cs.includes(c)) && out.length === rev.length;
      }),
    );
  });
  it("puts each chain on the map at the exported location (block level stays as exported) and leaves out chains with none", () => {
    const rows = chainRows([chain({ block_level: true, lat: 42.31, lon: -71.11 }), chain({ chain_id: "x", lat: undefined, lon: undefined })]);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ id: "c1", lat: 42.31, lon: -71.11, tier: "headline" });
  });
  it("finds the earliest headline zombie of a chain", () => {
    const z = (id: string, chain_id: string, tier: string, d: string) => ({ zombie_id: id, chain_id, tier, resurrection_date: d }) as unknown as Zombie;
    const out = firstZombieOfChain("c1", [z("b", "c1", "headline", "2020-05-01"), z("a", "c1", "headline", "2020-02-01"), z("s", "c1", "source_unknown", "2019-01-01"), z("o", "c2", "headline", "2018-01-01")]);
    expect(out?.zombie_id).toBe("a");
    expect(firstZombieOfChain("none", [])).toBeNull();
  });
});
