import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AutopsyCard, type CardWithPartial } from "../components/AutopsyCard";
import { splitObjections } from "../lib/autopsy";

/**
 * REQ-WEB-JUDGE.1, REQ-WEB-CARD.1 (design review 5, 13): the tour's cards come from the frozen judging snapshot, the committed
 * `data/judging/` folder (points.json, stats/judge_tour.json and one card shard per neighborhood and year). This reads those files
 * as they are: each tour zombie has a card there, the card shows a Second opinion exactly when the Skeptic recorded an objection,
 * and a record-confirmed tour stamps RECORD-CONFIRMED on every card.
 */
const root = join(__dirname, "..", "..", "..", "data", "judging");
const tourFile = join(root, "stats", "judge_tour.json");

describe.skipIf(!existsSync(tourFile))("the judge tour's cards in data/judging (REQ-WEB-JUDGE.1)", () => {
  const tour = existsSync(tourFile) ? JSON.parse(readFileSync(tourFile, "utf8")) : { zombie_ids: [] };
  const ids: string[] = tour.zombie_ids;
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
  it("shows the Second opinion on a tour card exactly when the Skeptic recorded an objection", () => {
    for (const id of ids) {
      const card = cards.get(id) as CardWithPartial;
      const objections = splitObjections(card.skeptic_notes);
      const { unmount } = render(<AutopsyCard card={card} />);
      const view = within(screen.getByTestId("autopsy-card"));
      if (objections.length > 0) expect(within(view.getByTestId("second-opinion")).getByText(objections[0]), id).toBeTruthy();
      else expect(view.queryByTestId("second-opinion"), id).toBeNull();
      unmount();
    }
  });
  it("stamps every card RECORD-CONFIRMED when the tour file says it is confirmed by the city's records", () => {
    const confirmed = tour.provisional === false && tour.confirmation === "records";
    for (const id of ids) {
      const { unmount } = render(<AutopsyCard card={cards.get(id) as CardWithPartial} recordConfirmed={confirmed} />);
      expect(screen.getByTestId("verdict-stamp").textContent, id).toBe(confirmed ? "Status: RECORD-CONFIRMED" : "Status: POSSIBLE");
      unmount();
    }
  });
});
