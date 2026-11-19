import { useEffect, useLayoutEffect, useRef } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { AutopsyCard, type CardWithPartial } from "../components/AutopsyCard";
import { PanelError } from "../components/PanelError";
import { useData } from "../lib/data";
import { usePoints } from "../lib/shards";
import { isFixtureData } from "../lib/dataAsOf";
import { parseCardShard, parsePoints, parseStatus } from "../lib/parse";
import { shardFile } from "../lib/shard";
import { t } from "../lib/t";

/**
 * The autopsy card as a nested route over the map (REQ-WEB-CARD.1, .4, .5). It loads the card's shard only when
 * opened. Wide screens: a side panel. Under 640 px: a bottom sheet with one readable copy (CSS).
 */
export default function CardRoute() {
  const { id: rawId } = useParams();
  const id = rawId ? decodeURIComponent(rawId) : "";
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const head = useData("points.json", parsePoints);
  // a card of another tier is not in the headline points: look in every tier before saying it is missing
  const inHeadline = head.status === "ok" && head.data.id.includes(id);
  const more = usePoints(head.status === "ok" && !inHeadline);
  const points = more.pending ? ({ status: "loading" } as const) : more.load;
  const index = points.status === "ok" ? points.data.id.indexOf(id) : -1;
  const file = points.status === "ok" && index >= 0 ? shardFile(points.data.neighborhood[index], points.data.year[index]) : null;
  const shard = useData(file, parseCardShard);
  const status = useData("status.json", parseStatus);
  const fixture = status.status === "ok" && isFixtureData(status.data);
  const card = shard.status === "ok" ? (shard.data.cards.find((c) => c.zombie_id === id) as CardWithPartial | undefined) : undefined;

  const heading = useRef<HTMLHeadingElement>(null);
  const close = () => navigate({ pathname: "/", search: params.toString() });

  useEffect(() => {
    const before = document.activeElement as HTMLElement | null;
    heading.current?.focus();
    return () => before?.focus?.();
  }, []);

  // Escape closes the card. Registered once, before the first paint, and reading the latest search through a ref: re-registering
  // on every change left a gap in which an Escape pressed as soon as the card showed was lost (an e2e test caught it 1 time in 6).
  const closeRef = useRef(close);
  closeRef.current = close;
  useLayoutEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeRef.current();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const missing = (points.status === "ok" && index < 0) || (shard.status === "ok" && !card);
  return (
    <div className="card-host" role="dialog" aria-modal="false" aria-labelledby="card-title">
      <div className="card-bar">
        <h2 id="card-title" tabIndex={-1} ref={heading}>
          {t("card.title")}
        </h2>
        <button type="button" onClick={close}>
          {t("card.close")}
        </button>
      </div>
      {fixture && (
        <p className="card-fixture-notice" data-testid="card-fixture-notice" role="note">
          {t("card.fixture_notice")}
        </p>
      )}
      {(points.status === "loading" || shard.status === "loading") && !missing && <p>{t("card.loading")}</p>}
      {points.status === "error" && <PanelError file={points.file} error={points.error} />}
      {shard.status === "error" && <PanelError file={shard.file} error={shard.error} />}
      {missing && <p className="panel-error">{t("card.not_found", { id })}</p>}
      {card && <AutopsyCard card={card} />}
    </div>
  );
}
