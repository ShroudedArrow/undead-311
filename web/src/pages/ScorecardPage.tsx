import { PanelError } from "../components/PanelError";
import { Scorecard } from "../components/Scorecard";
import { useData } from "../lib/data";
import { parseExcess, parseScorecard } from "../lib/parse";
import { t } from "../lib/t";

export default function ScorecardPage() {
  const card = useData("scorecard.json", parseScorecard);
  const excess = useData("excess.json", parseExcess);
  return (
    <div className="page">
      <h1>{t("score.title")}</h1>
      {card.status === "error" && <PanelError file={card.file} error={card.error} />}
      {card.status === "ok" && <Scorecard file={card.data} excess={excess.status === "ok" ? excess.data : null} />}
      {card.status === "ok" && excess.status === "error" && <PanelError file={excess.file} error={excess.error} />}
    </div>
  );
}
