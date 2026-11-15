import { formatDateTime, formatDay, formatGap } from "../lib/format";
import type { Card, CaseRecord } from "../lib/parse";
import { t } from "../lib/t";
import { CardShare } from "./ShareLinks";
import { ReportError } from "./ReportError";

/** Cards may carry `confidence_partial` as an extra field (zombies.json has it; see the engine proposal). */
export type CardWithPartial = Card & { confidence_partial?: boolean };

function CaseBlock({ heading, rec }: { heading: string; rec: CaseRecord }) {
  return (
    <section className="case-record" aria-label={heading}>
      <h3>{heading}</h3>
      <dl>
        <dt>{t("card.case_id")}</dt>
        <dd>
          {rec.system === "legacy" ? (
            <a href={t("card.case_url", { id: rec.id })} target="_blank" rel="noreferrer" aria-label={t("card.view_case", { id: rec.id })}>
              {rec.id}
            </a>
          ) : (
            // Owner decision (ops#13): a new-system case gets no link until the city's page for it is verified.
            <span>{rec.id}</span>
          )}{" "}
          ({rec.system === "legacy" ? t("card.system_legacy") : t("card.system_new")})
          {rec.system === "legacy" ? null : (
            <p className="case-note" data-testid="new-case-note">
              {t("card.new_case_no_link")}
            </p>
          )}
        </dd>
        <dt>{t("card.type")}</dt>
        <dd>{rec.type_raw}</dd>
        {rec.street ? (
          <>
            <dt>{t("card.place")}</dt>
            <dd>{rec.street}</dd>
          </>
        ) : null}
        <dt>{t("card.opened")}</dt>
        <dd>{formatDateTime(rec.open_time)}</dd>
        <dt>{t("card.closed")}</dt>
        <dd>{rec.close_time ? formatDateTime(rec.close_time) : t("card.not_closed")}</dd>
        <dt>{t("card.closure_text")}</dt>
        <dd>{rec.closure_text ? rec.closure_text : t("card.no_closure_text")}</dd>
      </dl>
    </section>
  );
}

const VERDICTS = {
  survives: "card.verdict_survives",
  weakened: "card.verdict_weakened",
  explained_away: "card.verdict_explained_away",
  not_reviewed: "card.verdict_not_reviewed",
} as const;

/**
 * The autopsy report for one possible zombie, drawn as a triplicate city form (REQ-WEB-CARD.1-3, .6).
 * The typewriter face is applied only inside `.autopsy-form` (see app.css).
 */
export function AutopsyCard({ card }: { card: CardWithPartial }) {
  return (
    <article className="autopsy" data-testid="autopsy-card" data-tier={card.tier}>
      <div className="autopsy-form">
        <header className="autopsy-head">
          <p className="autopsy-intro">{t("card.intro")}</p>
          <p className="stamps" aria-hidden="false">
            <span className="stamp stamp-closed">{t("card.stamp_closed")}</span>
            <span className="stamp stamp-again">{t("card.stamp_again")}</span>
          </p>
        </header>

        {card.bulk_closure ? (
          <p className="bulk-warning" data-testid="bulk-warning">
            {t("card.bulk_warning")}
          </p>
        ) : null}
        {card.tier !== "headline" ? <p className="tier-note">{t(`card.tier_note_${card.tier}`)}</p> : null}

        <dl className="autopsy-facts">
          <div>
            <dt>{t("card.cause_of_death")}</dt>
            <dd>{t(`labels.${card.cause_of_death}`)}</dd>
          </div>
          <div>
            <dt>{t("card.time_in_grave")}</dt>
            <dd>{formatGap(card.gap_days)}</dd>
          </div>
          <div>
            <dt>{t("card.resurrection_date")}</dt>
            <dd>{formatDay(card.resurrection_date)}</dd>
          </div>
          <div>
            <dt>{t("card.confidence")}</dt>
            <dd>
              {t("card.confidence_value", { percent: Math.round(card.confidence * 100) })}
              {card.confidence_partial ? <span className="partial-note"> {t("card.confidence_partial")}</span> : null}
            </dd>
          </div>
          {card.reports_after && card.reports_after > 1 ? (
            <div>
              <dt>{t("card.reports_since")}</dt>
              <dd>{card.reports_after}</dd>
            </div>
          ) : null}
        </dl>

        <section className="skeptic" aria-label={t("card.skeptic")}>
          <h3>{t("card.skeptic")}</h3>
          <p>{card.skeptic_notes || t("card.no_notes")}</p>
          <p>
            <strong>{t("card.verdict")}:</strong> {t(VERDICTS[card.skeptic_verdict])}
          </p>
        </section>

        <div className="case-pair">
          <CaseBlock heading={t("card.original")} rec={card.original} />
          <CaseBlock heading={t("card.rereport")} rec={card.rereport} />
        </div>
        <p className="autopsy-report">
          <ReportError id={card.zombie_id} />
        </p>
        <CardShare zombieId={card.zombie_id} />
      </div>
    </article>
  );
}
