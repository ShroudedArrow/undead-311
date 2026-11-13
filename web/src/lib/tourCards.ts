import { useEffect, useState } from "react";
import type { CardWithPartial } from "../components/AutopsyCard";
import { loadOnce } from "./data";
import { parseCardShard, parsePoints } from "./parse";
import { shardFile } from "./shard";

export type TourCards = { status: "loading" } | { status: "ok"; cards: CardWithPartial[] } | { status: "error"; file: string; error: string };

/** Load the cards for the tour's zombies: the points file once, then only the shards those zombies live in (REQ-WEB-CARD.4). */
export function useTourCards(ids: readonly string[] | null): TourCards {
  const [state, setState] = useState<TourCards>({ status: "loading" });
  const key = ids?.join("|") ?? "";
  useEffect(() => {
    if (!ids) return;
    let live = true;
    void (async () => {
      const pts = await loadOnce("points.json", parsePoints);
      if (pts.status !== "ok") return live && setState(pts.status === "error" ? pts : { status: "loading" });
      const out: CardWithPartial[] = [];
      for (const id of ids) {
        const i = pts.data.id.indexOf(id);
        if (i < 0) return live && setState({ status: "error", file: "points.json", error: `${id} is not in the points file` });
        const file = shardFile(pts.data.neighborhood[i], pts.data.year[i]);
        const shard = await loadOnce(file, parseCardShard);
        if (shard.status !== "ok") return live && setState(shard.status === "error" ? shard : { status: "loading" });
        const card = shard.data.cards.find((c) => c.zombie_id === id);
        if (!card) return live && setState({ status: "error", file, error: `${id} is not in this shard` });
        out.push(card as CardWithPartial);
      }
      if (live) setState({ status: "ok", cards: out });
    })();
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return state;
}
