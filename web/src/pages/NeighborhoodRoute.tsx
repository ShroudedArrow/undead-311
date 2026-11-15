import { Navigate, useParams } from "react-router-dom";
import { PanelError } from "../components/PanelError";
import { useData } from "../lib/data";
import { DEFAULT_STATE, encodeState } from "../lib/url";
import { parsePoints } from "../lib/parse";
import { shareSlug } from "../lib/share";
import { t } from "../lib/t";

/** Permalink for a neighborhood (REQ-WEB-LINKS.1): `/neighborhood/<slug>` opens the map filtered to it. */
export default function NeighborhoodRoute() {
  const { slug = "" } = useParams();
  const points = useData("points.json", parsePoints);
  if (points.status === "loading") return <p className="page">{t("filters.loading")}</p>;
  if (points.status === "error") return <div className="page"><PanelError file={points.file} error={points.error} /></div>;
  const name = points.data.neighborhood.find((n) => n !== null && shareSlug(n) === shareSlug(slug));
  if (!name) return <div className="page"><p>{t("share.neighborhood_not_found")}</p></div>;
  return <Navigate replace to={{ pathname: "/", search: encodeState({ ...DEFAULT_STATE, filters: { ...DEFAULT_STATE.filters, neighborhoods: [name] } }) }} />;
}
