import { dataAsOfLabel, isFixtureData } from "../lib/dataAsOf";
import { useData } from "../lib/data";
import { parseStatus } from "../lib/parse";
import { t } from "../lib/t";

/**
 * REQ-WEB-FRESH.1: "Data as of <date>" from status.json, shown on every page. REQ-WEB-DATA.3, UX-4: while the data is a
 * fixture, a notice next to the date says the numbers are not detector output.
 */
export function DataAsOf() {
  const status = useData("status.json", parseStatus);
  const label = status.status === "ok" ? dataAsOfLabel(status.data) : status.status === "error" ? dataAsOfLabel(null) : "\u00a0";
  const fixture = status.status === "ok" && isFixtureData(status.data);
  return (
    <div className="data-status">
      <p className="data-as-of" data-testid="data-as-of" aria-live="polite">
        {label}
      </p>
      {fixture ? (
        <p className="fixture-notice" data-testid="fixture-notice" role="note">
          {t("app.fixture_notice")}
        </p>
      ) : null}
    </div>
  );
}
