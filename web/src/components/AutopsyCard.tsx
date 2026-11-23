import { useId, useState } from "react";
import { distanceApartM, formatDistance, splitObjections } from "../lib/autopsy";
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
        <dd>{rec.closure_text ? rec.closure_text : rec.closure_text_hidden ? t("card.closure_text_hidden") : t("card.no_closure_text")}</dd>
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

/** Objections shown before "Show more". */
const OBJECTIONS_SHOWN = 2;

/**
 * A small sketch in place of the body diagram on a postmortem form: the street as a band, the first report and the re-report as
 * markers with the distance between them. A sketch, not a map: the marker positions are fixed and the distance is the number.
 */
function LocationDiagram({ street, distance, samePoint }: { street: string | null | undefined; distance: string; samePoint: boolean }) {
  const label = t("card.diagram_label", { street: street || t("card.place"), distance });
  return (
    <figure className="autopsy-figure" data-testid="location-diagram">
      <svg viewBox="0 0 260 100" role="img" aria-label={label} focusable="false">
        <rect x="4" y="46" width="252" height="22" className="diagram-street" />
        <line x1="10" y1="57" x2="250" y2="57" className="diagram-centerline" />
        {samePoint ? null : (
          <>
            <line x1="60" y1="26" x2="200" y2="26" className="diagram-dimension" />
            <line x1="60" y1="20" x2="60" y2="32" className="diagram-dimension" />
            <line x1="200" y1="20" x2="200" y2="32" className="diagram-dimension" />
          </>
        )}
        <text x="130" y="15" textAnchor="middle" className="diagram-text">
          {distance}
        </text>
        <circle cx={samePoint ? 124 : 60} cy="57" r="9" className="diagram-first" />
        <circle cx={samePoint ? 136 : 200} cy="57" r="10" className="diagram-again" />
        <text x={samePoint ? 118 : 60} y="88" textAnchor={samePoint ? "end" : "middle"} className="diagram-text">
          {t("card.diagram_first")}
        </text>
        <text x={samePoint ? 142 : 200} y="88" textAnchor={samePoint ? "start" : "middle"} className="diagram-text">
          {t("card.diagram_again")}
        </text>
      </svg>
      <figcaption>{street ? t("card.diagram_caption", { street }) : t("card.diagram_caption_nostreet")}</figcaption>
    </figure>
  );
}

/**
 * The Skeptic's second opinion. It appears only when the Skeptic recorded at least one objection for this zombie: most cards have
 * none (the Skeptic reviewed only the highest-ranked candidates), and an empty section or a "not reviewed" line says nothing.
 */
function SecondOpinion({ card }: { card: CardWithPartial }) {
  const [all, setAll] = useState(false);
  const listId = useId();
  const objections = splitObjections(card.skeptic_notes);
  if (objections.length === 0) return null;
  const hidden = Math.max(0, objections.length - OBJECTIONS_SHOWN);
  const shown = all ? objections : objections.slice(0, OBJECTIONS_SHOWN);
  return (
    <section className="skeptic" aria-label={t("card.skeptic")} data-testid="second-opinion">
      <h3>{t("card.skeptic")}</h3>
      <p className="skeptic-label">{t("card.skeptic_label")}</p>
      <ul className="skeptic-list" id={listId}>
        {shown.map((o) => (
          <li key={o}>{o}</li>
        ))}
      </ul>
      {hidden > 0 ? (
        <button type="button" className="skeptic-more" aria-expanded={all} aria-controls={listId} onClick={() => setAll(!all)}>
          {all ? t("card.show_fewer") : t("card.show_more", { count: hidden })}
        </button>
      ) : null}
      <p>
        <strong>{t("card.verdict")}:</strong> {t(VERDICTS[card.skeptic_verdict])}
      </p>
      <p className="skeptic-byline">{t("card.skeptic_byline")}</p>
    </section>
  );
}

/**
 * The autopsy report for one possible zombie, drawn as a triplicate city form that reads as a mock postmortem report
 * (REQ-WEB-CARD.1-3, .6). The report is fictional: no agency name, seal or official mark. Field labels carry the theme; every value
 * is a plain fact. The typewriter face is applied only inside `.autopsy-form` (see app.css). `recordConfirmed` is set for the
 * judge-tour zombies whose re-report the city's own closure shows was repaired again; every other card says POSSIBLE.
 */
export function AutopsyCard({ card, recordConfirmed = false }: { card: CardWithPartial; recordConfirmed?: boolean }) {
  const meters = distanceApartM(card.original, card.rereport);
  const distance = meters === null ? null : formatDistance(meters);
  const sameType = card.original.type_raw === card.rereport.type_raw;
  const decedent = [card.original.type_raw, card.original.street].filter(Boolean).join(", ");
  return (
    <article className="autopsy" data-testid="autopsy-card" data-tier={card.tier}>
      <div className="autopsy-form">
        <header className="autopsy-head">
          <div className="autopsy-heading">
            <p className="autopsy-title">{t("card.report_title")}</p>
            <p className="autopsy-meta">
              <span>{t("card.case_no", { id: card.rereport.id })}</span> <span>{t("card.page_of")}</span>
            </p>
          </div>
          <p className={recordConfirmed ? "stamp stamp-verdict stamp-confirmed" : "stamp stamp-verdict"} data-testid="verdict-stamp">
            <span className="visually-hidden">{t("card.status_label")} </span>
            {t(recordConfirmed ? "card.stamp_record_confirmed" : "card.stamp_possible")}
          </p>
        </header>
        <p className="autopsy-intro">{t("card.intro")}</p>
        <p className="stamps" aria-hidden="false">
          <span className="stamp stamp-closed">{t("card.stamp_closed")}</span>
          <span className="stamp stamp-again">{t("card.stamp_again")}</span>
        </p>

        {card.bulk_closure ? (
          <p className="bulk-warning" data-testid="bulk-warning">
            {t("card.bulk_warning")}
          </p>
        ) : null}
        {card.tier !== "headline" ? <p className="tier-note">{t(`card.tier_note_${card.tier}`)}</p> : null}

        <dl className="autopsy-facts">
          <div className="field-wide">
            <dt>{t("card.decedent")}</dt>
            <dd>{decedent}</dd>
          </div>
          <div>
            <dt>{t("card.date_of_death")}</dt>
            <dd>{card.original.close_time ? formatDay(card.original.close_time) : t("card.not_closed")}</dd>
          </div>
          <div>
            <dt>{t("card.date_of_resurrection")}</dt>
            <dd>{formatDay(card.resurrection_date)}</dd>
          </div>
          <div>
            <dt>{t("card.time_in_grave")}</dt>
            <dd>{formatGap(card.gap_days)}</dd>
          </div>
          <div>
            <dt>{t("card.cause_of_death")}</dt>
            <dd>{t(`labels.${card.cause_of_death}`)}</dd>
          </div>
          <div className="field-wide">
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
          <div className="field-wide" data-testid="findings">
            <dt>{t("card.findings")}</dt>
            <dd>
              <span className="finding">
                {sameType
                  ? t("card.finding_same_type", { type: card.original.type_raw })
                  : t("card.finding_diff_type", { first: card.original.type_raw, second: card.rereport.type_raw })}
              </span>{" "}
              {distance === null ? null : (
                <span className="finding">{meters !== null && meters < 0.5 ? t("card.finding_same_point") : t("card.finding_distance", { distance })}</span>
              )}
            </dd>
          </div>
        </dl>

        {distance === null ? null : <LocationDiagram street={card.original.street} distance={distance} samePoint={meters !== null && meters < 5} />}

        <SecondOpinion card={card} />

        <div className="case-pair">
          <CaseBlock heading={t("card.original")} rec={card.original} />
          <CaseBlock heading={t("card.rereport")} rec={card.rereport} />
        </div>
        <p className="autopsy-signature">{t("card.examined_by")}</p>
        <p className="autopsy-report">
          <ReportError id={card.zombie_id} />
        </p>
        <CardShare zombieId={card.zombie_id} />
      </div>
    </article>
  );
}
