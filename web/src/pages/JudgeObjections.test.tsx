import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AutopsyCard, type CardWithPartial } from "../components/AutopsyCard";
import { splitObjections } from "../lib/autopsy";

/**
 * REQ-WEB-JUDGE.1, REQ-WEB-CARD.1 (design review 5): the tour's cards come from the frozen judging snapshot, which is the committed
 * `data/judging/` folder (points.json, stats/judge_tour.json and one card shard per neighborhood and year). Each tour zombie must
 * carry a Skeptic objection there, so the tour shows its second opinion on every card.
 */
const root = join(__dirname, "..", "..", "..", "data", "judging");
const tourFile = join(root, "stats", "judge_tour.json");

describe.skipIf(!existsSync(tourFile))("the judge tour's cards in data/judging (REQ-WEB-JUDGE.1)", () => {
  const ids: string[] = existsSync(tourFile) ? JSON.parse(readFileSync(tourFile, "utf8")).zombie_ids : [];
  const cards = new Map<string, CardWithPartial>();
  if (existsSync(join(root, "cards"))) {
    for (const f of readdirSync(join(root, "cards"))) {
      for (const c of JSON.parse(readFileSync(join(root, "cards", f), "utf8")).cards as CardWithPartial[]) if (ids.includes(c.zombie_id)) cards.set(c.zombie_id, c);
    }
  }
  it("holds a card for every tour zombie", () => {
    expect(ids).toHaveLength(3);
    expect([...cards.keys()].sort()).toEqual([...ids].sort());
  });
  it("gives every tour zombie at least one Skeptic objection, and the card shows it", () => {
    for (const id of ids) {
      const card = cards.get(id) as CardWithPartial;
      const objections = splitObjections(card.skeptic_notes);
      expect(objections.length, id).toBeGreaterThan(0);
      const { unmount } = render(<AutopsyCard card={card} />);
      const section = within(screen.getByTestId("autopsy-card")).getByTestId("second-opinion");
      expect(within(section).getByText(objections[0]), id).toBeTruthy();
      unmount();
    }
  });
});
