import { Link } from "react-router-dom";
import { isFixtureData } from "../lib/dataAsOf";
import { useData } from "../lib/data";
import { familyLabel } from "../lib/labels";
import { parseBulkClosures, parseExclusions, parseStatus, parseTemporaryFixes, type Rate } from "../lib/parse";
import { pct } from "../lib/rates";
import { t } from "../lib/t";
import { PanelError } from "./PanelError";

function RateWithInterval({ rate }: { rate: Rate }) {
  if (rate.rate === null || rate.lo === null || rate.hi === null) return <>{t("deaths.temp_none")}</>;
  return (
    <>
      {pct(rate.rate)} ({t("charts.interval_text", { lo: pct(rate.lo), hi: pct(rate.hi) })}), {t("score.n", { n: rate.n })}
    </>
  );
}

const REASONS = ["excluded_type", "unlisted_type", "null_coords", "out_of_bounds", "placeholder", "null_open_time"];
const PAIR_REASONS = ["mirror", "transferred_original", "linked_successor"];

/**
 * What the headline leaves out (REQ-WEB-DEATHS.1): separate deaths, temporary-fix return rates, exclusions, the
 * source_unknown explanation and the bulk-closure days. Every panel loads its own file, so one failure hides only itself.
 */
export function LeavesOut() {
  const temp = useData("temporary_fixes.json", parseTemporaryFixes);
  const excl = useData("exclusions.json", parseExclusions);
  const bulk = useData("bulk_closures.json", parseBulkClosures);
  const status = useData("status.json", parseStatus);
  const unknown = status.status === "ok" ? (status.data.source_unknown_count ?? 0) : null;
  return (
    <section className="chart-section" aria-labelledby="leaves-out-h" data-testid="leaves-out">
      <h2 id="leaves-out-h">{t("deaths.heading")}</h2>
      <p>{t("deaths.intro")}</p>

      <h3>{t("deaths.sep_heading")}</h3>
      {temp.status === "error" && <PanelError file={temp.file} error={temp.error} />}
      {temp.status === "ok" && (
        <>
          <p data-testid="separate-deaths">{t("deaths.sep_text", { invalid: temp.data.separate_deaths.invalid, duplicate: temp.data.separate_deaths.duplicate })}</p>
          <h3>{t("deaths.temp_heading")}</h3>
          <p>{t("deaths.temp_text")}</p>
          <div className="table-wrap chart-table" tabIndex={0} role="region" aria-label={t("deaths.temp_caption")}>
            <table className="zombie-table" data-testid="temp-fixes">
              <caption>{t("deaths.temp_caption")}</caption>
              <thead>
                <tr>
                  <th scope="col">{t("deaths.col_family")}</th>
                  <th scope="col">{t("deaths.col_made_safe")}</th>
                  <th scope="col">{t("deaths.col_back")}</th>
                  <th scope="col">{t("deaths.col_unknown")}</th>
                </tr>
              </thead>
              <tbody>
                {temp.data.rows.map((r) => (
                  <tr key={`${r.family}|${r.department ?? ""}`}>
                    <th scope="row">{familyLabel(r.family)}</th>
                    <td>{r.n_made_safe}</td>
                    <td><RateWithInterval rate={r.after_temporary_fix} /></td>
                    <td><RateWithInterval rate={r.source_unknown} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <h3>{t("deaths.excl_heading")}</h3>
      {excl.status === "error" && <PanelError file={excl.file} error={excl.error} />}
      {excl.status === "ok" && status.status === "ok" && isFixtureData(status.data) ? <p className="count-note" data-testid="excl-fixture-note">{t("deaths.excl_fixture_note")}</p> : null}
      {excl.status === "ok" && (
        <div className="table-wrap chart-table" tabIndex={0} role="region" aria-label={t("deaths.excl_caption")}>
          <table className="zombie-table" data-testid="exclusions">
            <caption>{t("deaths.excl_caption")}</caption>
            <thead>
              <tr>
                <th scope="col">{t("deaths.col_reason")}</th>
                <th scope="col">{t("deaths.col_count")}</th>
              </tr>
            </thead>
            <tbody>
              {[...REASONS.map((k) => [k, excl.data.counts[k]] as const), ...PAIR_REASONS.map((k) => [k, excl.data.excluded_pairs[k]] as const)]
                .filter(([, n]) => n !== undefined)
                .map(([k, n]) => (
                  <tr key={k}>
                    <th scope="row">{t(`deaths.reason_${k}`)}</th>
                    <td>{n}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      )}

      <h3>{t("deaths.source_unknown_heading")}</h3>
      <p data-testid="source-unknown-text">
        {t("deaths.source_unknown_text", { count: unknown === null ? "" : unknown })}{" "}
        <Link to="/?tier=all">{t("deaths.source_unknown_link")}</Link>
      </p>

      <h3>{t("deaths.bulk_heading")}</h3>
      <p>{t("deaths.bulk_text")}</p>
      {bulk.status === "error" && <PanelError file={bulk.file} error={bulk.error} />}
      {bulk.status === "ok" &&
        (bulk.data.bulk_closures.length === 0 ? (
          <p data-testid="bulk-none">{t("deaths.bulk_none")}</p>
        ) : (
          <div className="table-wrap chart-table" tabIndex={0} role="region" aria-label={t("deaths.bulk_caption")}>
            <table className="zombie-table" data-testid="bulk-table">
              <caption>{t("deaths.bulk_caption")}</caption>
              <thead>
                <tr>
                  <th scope="col">{t("deaths.bulk_col_department")}</th>
                  <th scope="col">{t("deaths.bulk_col_day")}</th>
                  <th scope="col">{t("deaths.bulk_col_template")}</th>
                  <th scope="col">{t("deaths.bulk_col_cases")}</th>
                  <th scope="col">{t("deaths.bulk_col_usual")}</th>
                </tr>
              </thead>
              <tbody>
                {bulk.data.bulk_closures.map((b) => (
                  <tr key={`${b.department}|${b.close_date}|${b.template}`}>
                    <th scope="row">{b.department}</th>
                    <td>{b.close_date}</td>
                    <td>{b.template}</td>
                    <td>{b.n_cases}</td>
                    <td>{b.usual_daily}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      {bulk.status === "ok" && bulk.data.bulk_closures.length > 0 ? (
        <p>
          <Link to="/?bulk=1">{t("deaths.bulk_layer_link")}</Link>
        </p>
      ) : null}
    </section>
  );
}
