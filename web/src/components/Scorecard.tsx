import { familyLabel } from "../lib/labels";
import type { ExcessFile, ExcessRow, ScorecardFile } from "../lib/parse";
import { excessShown, familyExcessRows, num1 } from "../lib/methods";
import { headlineScorecards, stayedFixedShown } from "../lib/rates";
import { t } from "../lib/t";
import { RateCell } from "./RateCell";

/**
 * The excess with and without bursty spots for one case type (methods.md: "The scorecard reports the excess with and without
 * flagged spots, and the excess is never the headline number"; REQ-STAT-BASE.2, issue 130 in the ops repo). It sits below the two rates, as a detail.
 */
export function ExcessLines({ row }: { row: ExcessRow }) {
  const n = row.n_originals ?? 0;
  const w = row.without_bursty;
  const interval = (r: { excess: number; lo: number; hi: number; observed: number; expected: number }, n: number) => ({
    excess: num1(r.excess), lo: num1(r.lo), hi: num1(r.hi), observed: num1(r.observed), expected: num1(r.expected), n,
  });
  return (
    <div className="score-excess" data-testid="score-excess">
      <h3>{t("score.excess_heading")}</h3>
      <p data-testid="excess-all">{t("score.excess_all", interval(row, n))}</p>
      <p data-testid="excess-without">{w ? t("score.excess_without", interval(w, w.n_originals)) : t("score.excess_without_none")}</p>
      {row.n_bursty ? <p className="count-note" data-testid="excess-bursty">{t("score.excess_bursty_share", { bursty: row.n_bursty, n })}</p> : null}
    </div>
  );
}

/** On-time next to stayed-fixed for each case type and citywide, with intervals and n (REQ-WEB-SCORE.1-2). */
export function Scorecard({ file, excess }: { file: ScorecardFile; excess?: ExcessFile | null }) {
  const rows = headlineScorecards(file.scorecards);
  // methods.md: no excess anywhere when the headline placebo does not cover 0
  const excessByFamily = new Map((excess && excessShown(excess) ? familyExcessRows(excess) : []).map((r) => [r.name, r]));
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
                <RateCell label={t("score.label_raw")} rate={shown.rate} />
              </div>
              {excessByFamily.get(s.family) ? <ExcessLines row={excessByFamily.get(s.family) as ExcessRow} /> : null}
            </li>
          );
        })}
      </ul>
      <p className="count-note">{t("score.floor")}</p>
      {excessByFamily.size > 0 ? <p className="count-note">{t("score.excess_note")}</p> : null}
    </div>
  );
}
