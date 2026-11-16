import corrections from "../generated/corrections.json";
import { ReportError } from "../components/ReportError";
import { t } from "../lib/t";

export interface CorrectionsLog {
  title: string;
  intro: string[];
  rows: { date: string; wrong: string; fix: string }[];
}

/** Public corrections log, rendered from docs/CORRECTIONS.md at build time (REQ-WEB-FRESH.3). */
export function CorrectionsView({ log }: { log: CorrectionsLog }) {
  return (
    <div className="page">
      <h1>{t("corrections.title")}</h1>
      {log.intro.map((p) => (
        <p key={p}>{p}</p>
      ))}
      <p>
        <ReportError page={t("corrections.title")} />
      </p>
      {log.rows.length === 0 ? (
        <p data-testid="corrections-empty">{t("corrections.empty")}</p>
      ) : (
        <div className="table-wrap chart-table" tabIndex={0} role="region" aria-label={t("corrections.caption")}>
          <table className="zombie-table" data-testid="corrections-table">
            <caption>{t("corrections.caption")}</caption>
            <thead>
              <tr>
                <th scope="col">{t("corrections.col_date")}</th>
                <th scope="col">{t("corrections.col_wrong")}</th>
                <th scope="col">{t("corrections.col_fix")}</th>
              </tr>
            </thead>
            <tbody>
              {log.rows.map((r, i) => (
                <tr key={`${r.date}|${i}`}>
                  <td>{r.date}</td>
                  <td>{r.wrong}</td>
                  <td>{r.fix}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function CorrectionsPage() {
  return <CorrectionsView log={corrections as CorrectionsLog} />;
}
