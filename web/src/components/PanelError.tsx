import { t } from "../lib/t";

/** REQ-WEB-DATA.2: the error state for one panel; the rest of the page keeps working. */
export function PanelError({ file, error }: { file: string; error: string }) {
  return (
    <div className="panel-error" role="alert">
      <p>{t("errors.panel_failed")}</p>
      <p>{t("errors.panel_detail", { file, reason: error })}</p>
    </div>
  );
}
