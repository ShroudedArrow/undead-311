import type { ReactNode } from "react";
import { useData } from "../lib/data";
import { formatDate } from "../lib/dataAsOf";
import { parseStatus } from "../lib/parse";
import { t } from "../lib/t";

/**
 * The top of a plain page, drawn as the head of a form: the page title on the left and the date plaque on the right, the same
 * rubber-stamp plaque the time-lapse uses (design-system.md). The plaque holds only the date the records run to; the numbers
 * below it are plain facts. Pages put this first inside an element with the `form-sheet` class (app.css).
 */
export function PageHeader({ title, titleId, children }: { title: string; titleId?: string; children?: ReactNode }) {
  const status = useData("status.json", parseStatus);
  const date = status.status === "ok" ? formatDate(status.data.data_end ?? status.data.last_run) : null;
  return (
    <header className="form-head">
      <h1 id={titleId}>{title}</h1>
      <p className="plaque" data-testid="plaque" style={date ? undefined : { visibility: "hidden" }}>
        <span className="plaque-label">{t("theme.plaque_label")}</span>
        <span className="plaque-date">{date ?? "\u00a0"}</span>
      </p>
      {children}
    </header>
  );
}
