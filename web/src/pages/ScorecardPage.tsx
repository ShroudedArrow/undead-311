import { PanelError } from "../components/PanelError";
import { Scorecard } from "../components/Scorecard";
import { useData } from "../lib/data";
import { parseExcess, parseScorecard } from "../lib/parse";
import { t } from "../lib/t";

export default function ScorecardPage() {
  const card = useData("scorecard.json", parseScorecard);
  const excess = useData("excess.json", parseExcess);
  // Both files settle before anything is drawn: the excess lines under each rate would otherwise arrive later and push the rows apart.
  // Until then a screen-high placeholder holds the space, so nothing visible moves when they arrive (data-slot, app.css).
  const settled = card.status !== "loading" && excess.status !== "loading";
  return (
    <div className="page">
      <h1>{t("score.title")}</h1>
      <div data-slot={settled ? undefined : "page-loading"} aria-busy={!settled}>
        {!settled && <p className="count-note">{t("app.loading_section")}</p>}
        {settled && card.status === "error" && <PanelError file={card.file} error={card.error} />}
        {settled && card.status === "ok" && <Scorecard file={card.data} excess={excess.status === "ok" ? excess.data : null} />}
        {settled && card.status === "ok" && excess.status === "error" && <PanelError file={excess.file} error={excess.error} />}
      </div>
    </div>
  );
}
