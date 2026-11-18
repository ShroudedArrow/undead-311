import { t } from "../lib/t";

interface Props {
  /** Headline-tier count, always shown first (REQ-WEB-TIER.2). */
  headlineCount: number;
  /** All-tier count; given only while the sensitivity toggle is on, and always shown beside the headline count. */
  allCount?: number;
}

/** The count of possible zombies that match the filters, in the same set the map and table show (REQ-WEB-MAP.2-3, REQ-WEB-TIER.2). */
export function CountLine({ headlineCount, allCount }: Props) {
  return (
    <div className="count-block">
      <p className="count-line" data-testid="count" aria-live="polite">
        {headlineCount === 1 ? t("filters.count_headline_one") : t("filters.count_headline", { count: headlineCount })}
      </p>
      {allCount !== undefined ? (
        <p className="count-all" data-testid="count-all" aria-live="polite">
          {t("filters.count_all_tiers", { count: allCount })}
        </p>
      ) : null}
      <p className="count-note">{t("filters.count_floor")}</p>
    </div>
  );
}
