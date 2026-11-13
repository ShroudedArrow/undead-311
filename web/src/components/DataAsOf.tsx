import { dataAsOfLabel } from "../lib/dataAsOf";
import { useData } from "../lib/data";
import { parseStatus } from "../lib/parse";

/** REQ-WEB-FRESH.1: "Data as of <date>" from status.json, shown on every page. */
export function DataAsOf() {
  const status = useData("status.json", parseStatus);
  const label = status.status === "ok" ? dataAsOfLabel(status.data) : status.status === "error" ? dataAsOfLabel(null) : "\u00a0";
  return (
    <p className="data-as-of" data-testid="data-as-of" aria-live="polite">
      {label}
    </p>
  );
}
