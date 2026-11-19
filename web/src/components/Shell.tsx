import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { NavLink, Link, Outlet, useLocation } from "react-router-dom";
import { useLang } from "../lib/lang";
import { t } from "../lib/t";
import { DataAsOf } from "./DataAsOf";
import { Footer } from "./Footer";

/** Page frame on every route: skip link, header with nav and data date, footer (REQ-WEB-DESIGN.3, REQ-WEB-FRESH.1).
 * Under 640 px the links sit behind one Menu button so the map stays the first thing on the phone (REQ-WEB-MAP.1, UX-40). */
export function Shell() {
  const { lang, setLang, spanish } = useLang();
  const [open, setOpen] = useState(false);
  const toggle = useRef<HTMLButtonElement>(null);
  const header = useRef<HTMLElement>(null);
  // The header's height, as --site-header-h on the page root, so a page can fill exactly the rest of the screen (the time-lapse hero).
  useLayoutEffect(() => {
    const el = header.current;
    if (!el) return;
    const set = () => document.documentElement.style.setProperty("--site-header-h", `${Math.round(el.getBoundingClientRect().height)}px`);
    set();
    if (typeof ResizeObserver !== "function") return;
    const ro = new ResizeObserver(set);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const { pathname } = useLocation();
  useEffect(() => setOpen(false), [pathname]);
  // The map page (and its card route) fills the screen exactly: no page scroll, so nothing opened on it can move the map.
  const fit = pathname === "/" || pathname.startsWith("/zombie/");
  useEffect(() => {
    if (!open) return;
    // Escape hides the links, so focus goes back to the Menu button rather than dropping to the page body (UX-48).
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setOpen(false);
      toggle.current?.focus();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);
  return (
    <div className="shell" data-fit={fit ? "true" : undefined}>
      <a className="skip-link" href="#main">
        {t("app.skip_to_content")}
      </a>
      <header className="site-header on-dark" ref={header}>
        <p className="site-title">
          <Link to="/">{t("app.title")}</Link>
        </p>
        <button ref={toggle} type="button" className="nav-toggle" aria-expanded={open} aria-controls="site-nav" onClick={() => setOpen((o) => !o)}>
          {t("nav.menu")}
        </button>
        <nav id="site-nav" className="site-nav" data-open={open} aria-label={t("nav.label")}>
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
