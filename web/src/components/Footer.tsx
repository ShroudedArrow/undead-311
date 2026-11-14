import { t } from "../lib/t";

/** REQ-WEB-DESIGN.3: independence line, OSM credit and data licenses on every page. */
export function Footer() {
  return (
    <footer className="site-footer">
      <p>{t("app.footer_independent")}</p>
      <p>
        {t("app.footer_attribution")}{" "}
        <a href="https://www.openstreetmap.org/copyright" rel="noreferrer">
          openstreetmap.org/copyright
        </a>
      </p>
      <p>{t("app.footer_osm_license")}</p>
      <p>{t("app.footer_data_license")}</p>
      <p>{t("app.footer_fonts_license")}</p>
    </footer>
  );
}
