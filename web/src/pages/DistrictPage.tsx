import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import { PanelError } from "../components/PanelError";
import { useData } from "../lib/data";
import { familyLabel } from "../lib/labels";
import { districtsFromFile } from "../lib/openData";
import { parseDistricts } from "../lib/parse";
import { t } from "../lib/t";

/** Council district report cards (REQ-WEB-OPEN.2): a list of districts, and one printable page per district (print stylesheet in app.css). */
export default function DistrictPage() {
  const { id } = useParams();
  const zombies = useData("districts.json", parseDistricts);
  const all = useMemo(() => (zombies.status === "ok" ? districtsFromFile(zombies.data) : []), [zombies]);
  const one = id ? all.find((d) => d.district === decodeURIComponent(id)) : null;
  return (
    <div className="page district-page">
      {zombies.status === "error" && <PanelError file={zombies.file} error={zombies.error} />}
      {zombies.status === "ok" && !id && (
        <>
          <h1>{t("district.title")}</h1>
          <p>{t("district.intro")}</p>
          {all.length === 0 ? <p data-testid="district-none">{t("district.none")}</p> : (
            <div className="table-wrap" tabIndex={0} role="region" aria-label={t("district.list_caption")}>
              <table className="zombie-table" data-testid="district-list">
                <caption>{t("district.list_caption")}</caption>
                <thead><tr><th scope="col">{t("district.col_district")}</th><th scope="col">{t("district.col_count")}</th></tr></thead>
                <tbody>{all.map((d) => <tr key={d.district}><th scope="row"><Link to={`/districts/${encodeURIComponent(d.district)}`}>{d.district}</Link></th><td>{d.count}</td></tr>)}</tbody>
              </table>
            </div>
          )}
        </>
      )}
      {zombies.status === "ok" && id && !one && (
        <>
          <p data-testid="district-not-found">{t("district.not_found", { district: decodeURIComponent(id) })}</p>
          <p><Link to="/districts">{t("district.back")}</Link></p>
        </>
      )}
      {one && (
        <article data-testid="district-card">
          <h1>{t("district.card_title", { district: one.district })}</h1>
          <p className="district-total">{t("district.total", { count: one.count })}</p>
          <h2>{t("district.by_family")}</h2>
          <table className="zombie-table">
            <thead><tr><th scope="col">{t("district.col_family")}</th><th scope="col">{t("district.col_n")}</th></tr></thead>
            <tbody>{one.byFamily.map((f) => <tr key={f.family}><th scope="row">{familyLabel(f.family)}</th><td>{f.count}</td></tr>)}</tbody>
          </table>
          <h2>{t("district.by_year")}</h2>
          <table className="zombie-table">
            <thead><tr><th scope="col">{t("district.col_year")}</th><th scope="col">{t("district.col_n")}</th></tr></thead>
            <tbody>{one.byYear.map((y) => <tr key={y.year}><th scope="row">{y.year}</th><td>{y.count}</td></tr>)}</tbody>
          </table>
          <p className="count-note">{t("district.rates_missing")}</p>
          <p className="print-only">{t("district.printed_from")}</p>
          <p className="no-print">
            <button type="button" onClick={() => window.print()}>{t("district.print")}</button>{" "}
            <Link to="/districts">{t("district.back")}</Link>
          </p>
        </article>
      )}
    </div>
  );
}
