import { useEffect, useRef } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { AutopsyCard, type CardWithPartial } from "../components/AutopsyCard";
import { PanelError } from "../components/PanelError";
import { useData } from "../lib/data";
import { parseCardShard, parsePoints } from "../lib/parse";
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
  const points = useData("points.json", parsePoints);
  const index = points.status === "ok" ? points.data.id.indexOf(id) : -1;
  const file = points.status === "ok" && index >= 0 ? shardFile(points.data.neighborhood[index], points.data.year[index]) : null;
  const shard = useData(file, parseCardShard);
  const card = shard.status === "ok" ? (shard.data.cards.find((c) => c.zombie_id === id) as CardWithPartial | undefined) : undefined;

  const heading = useRef<HTMLHeadingElement>(null);
  const close = () => navigate({ pathname: "/", search: params.toString() });

  useEffect(() => {
    const before = document.activeElement as HTMLElement | null;
    heading.current?.focus();
    return () => before?.focus?.();
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") navigate({ pathname: "/", search: params.toString() });
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [navigate, params]);

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
      {(points.status === "loading" || shard.status === "loading") && !missing && <p>{t("card.loading")}</p>}
      {points.status === "error" && <PanelError file={points.file} error={points.error} />}
      {shard.status === "error" && <PanelError file={shard.file} error={shard.error} />}
      {missing && <p className="panel-error">{t("card.not_found", { id })}</p>}
      {card && <AutopsyCard card={card} />}
    </div>
  );
}
