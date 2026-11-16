import { dataAsOfLabel, isFixtureData, sampleCaseCount } from "../lib/dataAsOf";
import { useData } from "../lib/data";
import { parseStatus } from "../lib/parse";
import { t } from "../lib/t";

/**
 * REQ-WEB-FRESH.1: "Data as of <date>" from status.json, shown on every page. REQ-WEB-DATA.3, UX-4: while the data is a
 * fixture, a notice next to the date says the numbers are not detector output. ops issue 216: on a sample run, a notice says the
 * numbers come from the sample, not all of Boston.
 */
export function DataAsOf() {
  const status = useData("status.json", parseStatus);
  const label = status.status === "ok" ? dataAsOfLabel(status.data) : status.status === "error" ? dataAsOfLabel(null) : "\u00a0";
  const fixture = status.status === "ok" && isFixtureData(status.data);
  const sample = status.status === "ok" && !fixture ? sampleCaseCount(status.data) : null;
  return (
    <div className="data-status">
      <p className="data-as-of" aria-live="polite">
        <span data-testid="data-as-of">{label}</span>
        {sample !== null ? (
          <>
            {" "}
            <strong className="sample-note" data-testid="sample-notice" role="note">
              {t("app.sample_notice", { count: sample.toLocaleString("en-US") })}
            </strong>
          </>
        ) : null}
      </p>
      {fixture ? (
        <p className="fixture-notice" data-testid="fixture-notice" role="note">
          {t("app.fixture_notice")}
        </p>
      ) : null}
    </div>
  );
}
