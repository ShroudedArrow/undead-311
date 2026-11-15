import { describe, expect, it } from "vitest";
import en from "../copy/en.json";
import es from "../copy/es.json";
import { t } from "./t";
import { TIERS } from "./filter";

/** UX-53 (issue 198), REQ-WEB-COPY.1, REQ-WEB-TIER.1, REQ-WEB-CARD.1: a new tier can never render a raw copy key. */
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
});
