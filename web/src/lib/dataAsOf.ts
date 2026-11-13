import { t } from "./t";

/** Format an ISO date or timestamp as "Nov 13, 2026" in a fixed locale and UTC, so output never depends on the machine (REQ-WEB-FRESH.1). */
export function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat("en-US", { year: "numeric", month: "short", day: "numeric", timeZone: "UTC" }).format(d);
}

/** The "Data as of" label. Uses the data's own end date when present, else the last run date (REQ-WEB-FRESH.1). */
export function dataAsOfLabel(status: { data_end?: string; last_run: string; ok: boolean } | null): string {
  if (!status) return t("app.data_as_of_unknown");
  const date = formatDate(status.data_end ?? status.last_run);
  return t(status.ok ? "app.data_as_of" : "app.data_as_of_stale", { date });
}

/** True when the data is a stand-in built from the sample file, not detector output (REQ-WEB-DATA.3, UX-4). */
export function isFixtureData(status: { data_version: string } | null | undefined): boolean {
  return Boolean(status && status.data_version.startsWith("fixture-"));
}
