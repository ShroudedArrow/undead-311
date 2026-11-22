import { useEffect, useRef } from "react";
import { PAGE_SIZE } from "../lib/paging";
import { t } from "../lib/t";

/**
 * Status line and button under a long list. The button adds one page; when the last page is shown the button goes away and focus
 * moves to the status line, so a keyboard user is not dropped at the top of the page.
 */
export function ShowMore({ shown, total, onMore }: { shown: number; total: number; onMore: () => void }) {
  const shownNow = Math.min(shown, total);
  const remaining = total - shownNow;
  const status = useRef<HTMLParagraphElement>(null);
  const wasMore = useRef(remaining > 0);
  useEffect(() => {
    if (wasMore.current && remaining === 0) status.current?.focus();
    wasMore.current = remaining > 0;
  }, [remaining]);
  if (total <= PAGE_SIZE) return null;
  return (
    <div className="show-more">
      <p ref={status} tabIndex={-1} data-testid="show-status" aria-live="polite">
        {t("paging.showing", { shown: shownNow, total })}
      </p>
      {remaining > 0 && (
        <button type="button" onClick={onMore}>
          {t("paging.more", { count: Math.min(PAGE_SIZE, remaining) })}
        </button>
      )}
    </div>
  );
}
