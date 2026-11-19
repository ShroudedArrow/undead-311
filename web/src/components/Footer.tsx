import { useRef, useState } from "react";
import { readFooterCollapsed, writeFooterCollapsed } from "../lib/footerPref";
import { t } from "../lib/t";

/**
 * REQ-WEB-DESIGN.3: independence line, OSM credit and data licenses on every page.
 * The visitor can collapse the bar to a one-line note in the corner and reopen it; the choice is kept in localStorage.
 * `pinned` (the methods page) always shows the full bar with no close button, so the licenses stay in front of anyone reading the methods.
 */
export function Footer({ pinned = false }: { pinned?: boolean }) {
  const [collapsed, setCollapsed] = useState(readFooterCollapsed);
  const closeRef = useRef<HTMLButtonElement>(null);
  const noteRef = useRef<HTMLButtonElement>(null);
  const change = (next: boolean) => {
    setCollapsed(next);
    writeFooterCollapsed(next);
    // keep keyboard focus on the control that replaces the one just used
    requestAnimationFrame(() => (next ? noteRef : closeRef).current?.focus());
  };
  if (collapsed && !pinned) {
    return (
      <footer className="site-footer-note">
        <button ref={noteRef} type="button" aria-expanded={false} onClick={() => change(false)}>
          {t("app.footer_note")}
        </button>
      </footer>
    );
  }
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
      {pinned ? null : (
        <button ref={closeRef} type="button" className="footer-close" aria-expanded={true} aria-label={t("app.footer_close")} onClick={() => change(true)}>
          <span aria-hidden="true">×</span>
        </button>
      )}
    </footer>
  );
}
