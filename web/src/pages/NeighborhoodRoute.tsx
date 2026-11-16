import { Navigate, useParams } from "react-router-dom";
import { PanelError } from "../components/PanelError";
import { DEFAULT_STATE, encodeState } from "../lib/url";
import { useZombieIndex } from "../lib/shards";
import { shareSlug } from "../lib/share";
import { t } from "../lib/t";

/** Permalink for a neighborhood (REQ-WEB-LINKS.1): `/neighborhood/<slug>` opens the map filtered to it. */
export default function NeighborhoodRoute() {
  const { slug = "" } = useParams();
  const points = useZombieIndex();
  if (points.status === "loading") return <p className="page">{t("filters.loading")}</p>;
  if (points.status === "error") return <div className="page"><PanelError file={points.file} error={points.error} /></div>;
  const name = points.data.shards.map((s) => s.neighborhood).find((n) => n !== null && shareSlug(n) === shareSlug(slug));
  if (!name) return <div className="page"><p>{t("share.neighborhood_not_found")}</p></div>;
  return <Navigate replace to={{ pathname: "/", search: encodeState({ ...DEFAULT_STATE, filters: { ...DEFAULT_STATE.filters, neighborhoods: [name] } }) }} />;
}
