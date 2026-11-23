import { t } from "../lib/t";

/** One line above a table that is wider than a phone: the table scrolls sideways inside its box (shown under 640 px only, app.css). */
export function ScrollHint() {
  return <p className="scroll-hint count-note">{t("theme.scroll_hint")}</p>;
}
