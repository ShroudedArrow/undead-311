import { OpenData } from "../components/OpenData";
import { Sliders } from "../components/Sliders";
import { LeavesOut } from "../components/LeavesOut";
import { PanelError } from "../components/PanelError";
import { ReportError } from "../components/ReportError";
import { Link } from "react-router-dom";
import { useData } from "../lib/data";
import { sampleCaseCount } from "../lib/dataAsOf";
import { formatDateTime } from "../lib/format";
import { familyLabel } from "../lib/labels";
import { excessShown, familyExcessRows, num1, readPlacebo, readShift } from "../lib/methods";
import { NULL_TOWNS, STRESS_ABOVE, STRESS_TOWNS, signed, sumOf } from "../lib/nullTowns";
import { parseExcess, parseScorecard, parseStatus, parseValidation } from "../lib/parse";
import { pct } from "../lib/rates";
import { t } from "../lib/t";

function Definitions() {
  const card = useData("scorecard.json", parseScorecard);
  const p = card.status === "ok" ? card.data.params : null;
  const window = p?.WINDOW_DAYS ?? 60;
  const radius = p?.RADIUS_M ?? 30;
  return (
    <section className="chart-section" aria-labelledby="def-h">
      <h2 id="def-h">{t("methods.definitions_heading")}</h2>
      <ul className="plain-list">
        <li>{t("methods.def_scope")}</li>
        <li>{t("methods.def_incident")}</li>
        <li>{t("methods.def_window", { window })}</li>
        <li>{t("methods.def_place", { radius })}</li>
        <li>{t("methods.def_city")}</li>
        <li>{t("methods.def_mirror")}</li>
      </ul>
      {p ? <p className="count-note">{t("methods.def_params", { matching: p.matching, radius: p.RADIUS_M, window: p.WINDOW_DAYS })}</p> : null}
    </section>
  );
}

function Baselines() {
  const excess = useData("excess.json", parseExcess);
  const status = useData("status.json", parseStatus);
  const warning = status.status === "ok" ? status.data.calibration_warning : null;
  return (
    <section className="chart-section" aria-labelledby="base-h">
      <h2 id="base-h">{t("methods.baselines_heading")}</h2>
      <p>{t("methods.baselines_text")}</p>
      <p data-testid="excess-floor">{t("methods.excess_floor")}</p>
      {excess.status === "error" && <PanelError file={excess.file} error={excess.error} />}
      {excess.status === "ok" ? (
        <>
          {!excessShown(excess.data) ? (
            <p data-testid="excess-withheld">{t("methods.excess_withheld")}</p>
          ) : familyExcessRows(excess.data).length === 0 ? (
            <p>{t("methods.excess_missing")}</p>
          ) : (
            <div className="table-wrap chart-table" tabIndex={0} role="region" aria-label={t("methods.excess_caption")}>
              <table className="zombie-table" data-testid="excess-table">
                <caption>{t("methods.excess_caption")}</caption>
                <thead>
                  <tr>
                    <th scope="col">{t("methods.col_group")}</th>
                    <th scope="col">{t("methods.col_observed")}</th>
                    <th scope="col">{t("methods.col_expected")}</th>
                    <th scope="col">{t("methods.col_excess")}</th>
                    <th scope="col">{t("methods.col_interval")}</th>
                  </tr>
                </thead>
                <tbody>
                  {familyExcessRows(excess.data).map((r) => (
                    <tr key={r.name}>
                      <th scope="row">{familyLabel(r.name)}</th>
                      <td>{r.observed}</td>
                      <td>{num1(r.expected)}</td>
                      <td>{num1(r.excess)}</td>
                      <td>{t("charts.interval_text", { lo: num1(r.lo), hi: num1(r.hi) })}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <ShiftAndPlacebo file={excess.data} />
        </>
      ) : null}
      {warning ? <p className="calibration-warning" data-testid="calibration-warning" role="note">{t("methods.calibration_warning", { text: warning })}</p> : null}
    </section>
  );
}

/** Results on seeded towns where the true excess is 0 (owner decision, channel issue 130). The rows are pinned to docs/METHODS.md by a test. */
function NullTowns() {
  const towns = NULL_TOWNS.reduce((s, r) => s + r.below + r.covers + r.above, 0);
  return (
    <section className="chart-section" aria-labelledby="null-h" data-testid="null-towns">
      <h2 id="null-h">{t("methods.null_heading")}</h2>
      <p data-testid="null-summary">{t("methods.null_text", { towns, below: sumOf("below"), covers: sumOf("covers") })}</p>
      <div className="table-wrap chart-table" tabIndex={0} role="region" aria-label={t("methods.null_caption")}>
        <table className="zombie-table">
          <caption>{t("methods.null_caption")}</caption>
          <thead>
            <tr>
              <th scope="col">{t("methods.null_col_town")}</th>
              <th scope="col">{t("methods.null_col_range")}</th>
              <th scope="col">{t("methods.null_col_where")}</th>
            </tr>
          </thead>
          <tbody>
            {NULL_TOWNS.map((r) => (
              <tr key={r.id}>
                <th scope="row">{t(`methods.nt_${r.id}`)}</th>
                <td>{t("methods.null_range", { min: signed(r.min), max: signed(r.max) })}</td>
                <td>{t("methods.null_where", { below: r.below, n: r.below + r.covers + r.above, covers: r.covers })}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p>{t("methods.null_below_means")}</p>
      <p data-testid="null-limits">{t("methods.null_limits", { towns: STRESS_TOWNS, fine: STRESS_TOWNS - STRESS_ABOVE, above: STRESS_ABOVE })}</p>
    </section>
  );
}

function ShiftAndPlacebo({ file }: { file: Parameters<typeof readShift>[0] }) {
  const shift = readShift(file);
  const placebo = readPlacebo(file);
  return (
    <>
      <h3>{t("methods.shift_heading")}</h3>
      {shift ? (
        <>
          <p>{t("methods.shift_text", { runs: shift.runs, seed: shift.seed ?? "" })}</p>
          <ShiftBar shift={shift} />
          <p data-testid="shift-observed">{t("methods.shift_observed", { observed: shift.observed })}</p>
          <p data-testid="shift-range">{t("methods.shift_range", { mean: num1(shift.mean), lo: num1(shift.q025), hi: num1(shift.q975) })}</p>
        </>
      ) : (
        <p>{t("methods.shift_missing")}</p>
      )}
      <h3>{t("methods.placebo_heading")}</h3>
      <p>{t("methods.placebo_text")}</p>
      {placebo ? (
        <>
          <p data-testid="placebo">{t("methods.placebo_value", { excess: num1(placebo.excess), lo: num1(placebo.lo), hi: num1(placebo.hi) })}</p>
          {placebo.hi < 0 ? <p className="calibration-warning" role="note" data-testid="placebo-note">{t("methods.placebo_below")}</p> : null}
          {placebo.lo > 0 ? <p className="calibration-warning" role="note" data-testid="placebo-note">{t("methods.placebo_above")}</p> : null}
        </>
      ) : (
        <p>{t("methods.placebo_missing")}</p>
      )}
    </>
  );
}

/** The chance range (2.5% to 97.5% of shifted runs) with the mean, and the observed count as a line. Values are also written out below. */
function ShiftBar({ shift }: { shift: NonNullable<ReturnType<typeof readShift>> }) {
  const hi = Math.max(shift.observed, shift.q975) * 1.05 || 1;
  const x = (v: number) => (v / hi) * 100;
  return (
    <svg className="shift-bar" viewBox="0 0 100 14" role="img" aria-label={t("methods.shift_range", { mean: num1(shift.mean), lo: num1(shift.q025), hi: num1(shift.q975) })} focusable="false" preserveAspectRatio="none">
      <rect className="rate-track" x="0" y="6" width="100" height="2" />
      <rect className="rate-interval" x={x(shift.q025)} y="3" width={Math.max(0.8, x(shift.q975) - x(shift.q025))} height="8" />
      <rect className="rate-point" x={x(shift.mean) - 0.4} y="1" width="0.8" height="12" />
      <rect className="shift-observed-mark" x={x(shift.observed) - 0.5} y="0" width="1" height="14" />
    </svg>
  );
}

function Validation() {
  const v = useData("validation.json", parseValidation);
  return (
    <section className="chart-section" aria-labelledby="val-h">
      <h2 id="val-h">{t("methods.validation_heading")}</h2>
      {v.status === "error" && <PanelError file={v.file} error={v.error} />}
      {v.status === "ok" && (v.data.status === "awaiting_field_labels" || !v.data.precision || v.data.precision.rate === null) ? <p data-testid="validation-awaiting">{t("methods.validation_awaiting")}</p> : null}
      {v.status === "ok" && v.data.status === "scored" && v.data.precision && v.data.precision.rate !== null ? (
        <div data-testid="validation-scored">
          <p>{t("methods.validation_precision", { rate: pct(v.data.precision.rate), lo: pct(v.data.precision.lo), hi: pct(v.data.precision.hi), n: v.data.precision.n })}</p>
          {v.data.cant_tell_share !== null && v.data.cant_tell_share !== undefined ? <p>{t("methods.validation_cant_tell", { share: pct(v.data.cant_tell_share) })}</p> : null}
          {v.data.kappa !== null && v.data.kappa !== undefined ? <p>{t("methods.validation_kappa", { kappa: v.data.kappa.toFixed(2) })}</p> : null}
        </div>
      ) : null}
    </section>
  );
}

function Status() {
  const s = useData("status.json", parseStatus);
  return (
    <section className="chart-section" aria-labelledby="status-h">
      <h2 id="status-h">{t("methods.status_heading")}</h2>
      {s.status === "error" && <PanelError file={s.file} error={s.error} />}
      {s.status === "ok" ? (
        <div data-testid="nightly-status">
          <p>{t("methods.status_last_run", { date: formatDateTime(s.data.last_run) })}</p>
          <p>{s.data.ok ? t("methods.status_ok") : t("methods.status_failed")}</p>
          <p className="count-note">{t("methods.status_version", { version: s.data.data_version })}</p>
          <ul className="plain-list">
            {Object.entries(s.data.row_counts).sort().map(([k, n]) => (
              <li key={k}>{t("methods.status_rows", { name: k.replace(/_/g, " "), count: n })}</li>
            ))}
          </ul>
          <h3>{t("methods.status_anomalies")}</h3>
          {s.data.anomalies.length === 0 ? (
            <p>{t("methods.status_no_anomalies")}</p>
          ) : (
            <ul className="plain-list">{s.data.anomalies.map((a) => <li key={a}>{a}</li>)}</ul>
          )}
        </div>
      ) : null}
    </section>
  );
}

/** ops issue 216: on a sample run the methods page says, in its own words, that every number below comes from the sample. */
function MethodsSampleNotice() {
  const status = useData("status.json", parseStatus);
  const n = status.status === "ok" ? sampleCaseCount(status.data) : null;
  if (n === null) return null;
  return (
    <p className="fixture-notice" data-testid="methods-sample-notice" role="note">
      {t("methods.sample_notice", { count: n.toLocaleString("en-US") })}
    </p>
  );
}

/** Methods page: definitions, baselines, shift test, placebo, validation, limits, nightly status and what the headline leaves out (REQ-WEB-METHODS.1, REQ-WEB-FRESH.2, REQ-WEB-DEATHS.1). */
export default function MethodsPage() {
  return (
    <div className="page">
      <h1>{t("methods.title")}</h1>
      <MethodsSampleNotice />
      <p data-testid="methods-intro">{t("methods.intro")}</p>
      <Definitions />
      <Baselines />
      <NullTowns />
      <section className="chart-section" aria-labelledby="adjusted-h" data-testid="baseline-uses">
        <h2 id="adjusted-h">{t("methods.adjusted_heading")}</h2>
        <p data-testid="adjusted-text">{t("methods.adjusted_text")}</p>
        <p data-testid="confidence-text">{t("methods.confidence_text")}</p>
      </section>
      <Sliders />
      <Validation />
      <section className="chart-section" aria-labelledby="limits-h">
        <h2 id="limits-h">{t("methods.limits_heading")}</h2>
        <ul className="plain-list">
          <li>{t("methods.limit_floor")}</li>
          <li>{t("methods.limit_intersection")}</li>
          <li>{t("methods.limit_origin")}</li>
        </ul>
      </section>
      <LeavesOut />
      <OpenData />
      <Status />
      <section className="chart-section" aria-labelledby="report-h">
        <h2 id="report-h">{t("methods.report_heading")}</h2>
        <p>{t("methods.report_text")}</p>
        <p>
          <ReportError page={t("methods.title")} /> <Link to="/corrections">{t("links.corrections")}</Link>
        </p>
      </section>
    </div>
  );
}
