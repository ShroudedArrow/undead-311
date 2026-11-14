import { t } from "../lib/t";

/** Link to the public issue form, with the card or page named in the title (REQ-WEB-FRESH.3). Opens in a new tab so the card stays put. */
export function ReportError({ id, page }: { id?: string; page?: string }) {
  const title = id ? t("links.report_error_title", { id }) : t("links.report_error_title_page", { page: page ?? "" });
  const href = t("links.report_error_url", { title: encodeURIComponent(title) });
  return (
    <a className="report-error" href={href} target="_blank" rel="noreferrer">
      {t("links.report_error")}
    </a>
  );
}
