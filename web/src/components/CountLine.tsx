import { t } from "../lib/t";

/** The count of possible zombies that match the filters, in the same set the map and table show (REQ-WEB-MAP.2-3). */
export function CountLine({ count }: { count: number }) {
  return (
    <div>
      <p className="count-line" data-testid="count" aria-live="polite">
        {count === 1 ? t("filters.count_headline_one") : t("filters.count_headline", { count })}
      </p>
      <p className="count-note">{t("filters.count_floor")}</p>
    </div>
  );
}
