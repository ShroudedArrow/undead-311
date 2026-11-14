import { PanelError } from "../components/PanelError";
import { Scorecard } from "../components/Scorecard";
import { useData } from "../lib/data";
import { parseScorecard } from "../lib/parse";
import { t } from "../lib/t";

export default function ScorecardPage() {
  const card = useData("scorecard.json", parseScorecard);
  return (
    <div className="page">
      <h1>{t("score.title")}</h1>
      {card.status === "error" && <PanelError file={card.file} error={card.error} />}
      {card.status === "ok" && <Scorecard file={card.data} />}
    </div>
  );
}
