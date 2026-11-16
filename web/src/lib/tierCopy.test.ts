import { describe, expect, it } from "vitest";
import en from "../copy/en.json";
import es from "../copy/es.json";
import { t } from "./t";
import { readZombies } from "../test/zombieShards";
import { TIERS } from "./filter";

/** UX-53 (issue 198), UX-55 (issue 210): `Tier` is derived from `TIERS`, so the loop below covers every tier. REQ-WEB-COPY.1, REQ-WEB-TIER.1, REQ-WEB-CARD.1: a new tier can never render a raw copy key. */
describe("every tier has copy (REQ-WEB-TIER.1, REQ-WEB-COPY.1)", () => {
  for (const tier of TIERS) {
    it(`tier ${tier} has a short label`, () => {
      expect(t(`tiers.${tier}`)).not.toBe(`tiers.${tier}`);
      expect((en.tiers as Record<string, string>)[tier]).toBeTruthy();
    });
    if (tier !== "headline") {
      it(`tier ${tier} has a card note in English and Spanish (REQ-WEB-CARD.1)`, () => {
        expect(t(`card.tier_note_${tier}`)).not.toBe(`card.tier_note_${tier}`);
        expect((es.card as Record<string, string>)[`tier_note_${tier}`]).toBeTruthy();
      });
    }
  }
  it("the tier toggle help text names city re-reports (REQ-WEB-TIER.1)", () => {
    expect(t("filters.tier_toggle_note").toLowerCase()).toContain("city re-reports");
  });
  it("every tier in the exported zombies is a listed tier (UX-55, REQ-WEB-TIER.1)", () => {
    const file = readZombies();
    const seen = new Set(file.zombies.map((z) => z.tier));
    for (const tier of seen) expect(TIERS as readonly string[]).toContain(tier);
  });
});
