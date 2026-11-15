import { NavLink, Link, Outlet } from "react-router-dom";
import { useLang } from "../lib/lang";
import { t } from "../lib/t";
import { DataAsOf } from "./DataAsOf";
import { Footer } from "./Footer";

/** Page frame on every route: skip link, header with nav and data date, footer (REQ-WEB-DESIGN.3, REQ-WEB-FRESH.1). */
export function Shell() {
  const { lang, setLang, spanish } = useLang();
  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        {t("app.skip_to_content")}
      </a>
      <header className="site-header on-dark">
        <p className="site-title">
          <Link to="/">{t("app.title")}</Link>
        </p>
        <nav className="site-nav" aria-label={t("nav.label")}>
          <NavLink to="/" end>
            {t("nav.map")}
          </NavLink>
          <NavLink to="/street">{t("nav.street")}</NavLink>
          <NavLink to="/repeat">{t("nav.repeat")}</NavLink>
          <NavLink to="/timelapse">{t("nav.timelapse")}</NavLink>
          <NavLink to="/scorecard">{t("nav.scorecard")}</NavLink>
          <NavLink to="/durability">{t("nav.durability")}</NavLink>
          <NavLink to="/methods">{t("nav.methods")}</NavLink>
          <NavLink to="/judge">{t("nav.judge")}</NavLink>
        </nav>
        {spanish ? (
          <div className="lang-switch" role="group" aria-label={t("lang.label")}>
            {(["en", "es"] as const).map((l) => (
              <button key={l} type="button" lang={l} aria-pressed={lang === l} onClick={() => setLang(l)}>{t(`lang.${l}`)}</button>
            ))}
          </div>
        ) : null}
        <DataAsOf />
      </header>
      <main id="main" className="shell-main" tabIndex={-1}>
        <Outlet />
      </main>
      <Footer />
    </div>
  );
}
