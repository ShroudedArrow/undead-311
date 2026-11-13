import { familyLabel } from "../lib/labels";
import type { ScorecardFile } from "../lib/parse";
import { headlineScorecards, pct, stayedFixedShown } from "../lib/rates";
import { t } from "../lib/t";
import { RateCell } from "./RateCell";

/** On-time next to stayed-fixed for each case type and citywide, with intervals and n (REQ-WEB-SCORE.1-2). */
export function Scorecard({ file }: { file: ScorecardFile }) {
  const rows = headlineScorecards(file.scorecards);
  return (
    <div className="scorecard">
      <p>{t("score.intro")}</p>
      <p className="count-note">{t("score.counts", { headline: file.counts.headline, source_unknown: file.counts.source_unknown, sensitivity: file.counts.sensitivity })}</p>
      <ul className="score-list">
        {rows.map((s) => {
          const shown = stayedFixedShown(s);
          return (
            <li key={s.family} className="score-row" data-family={s.family}>
              <h2>{familyLabel(s.family)}</h2>
              <div className="score-pair">
                <RateCell label={t("score.on_time")} rate={s.on_time} />
                <RateCell label={t(shown.kind === "adjusted" ? "score.label_adjusted" : "score.label_raw")} rate={shown.rate} />
              </div>
              {shown.kind === "adjusted" ? (
                <details className="score-detail">
                  <summary>{t("score.show_raw")}</summary>
                  <p>
                    {t("score.raw_detail", {
                      rate: pct(s.stayed_fixed_raw.rate) || "n/a",
                      lo: pct(s.stayed_fixed_raw.lo) || "n/a",
                      hi: pct(s.stayed_fixed_raw.hi) || "n/a",
                      n: s.stayed_fixed_raw.n,
                    })}
                  </p>
                </details>
              ) : null}
            </li>
          );
        })}
      </ul>
      <p className="count-note">{t("score.floor")}</p>
    </div>
  );
}
