import { pct } from "../lib/rates";
import type { Rate } from "../lib/parse";
import { t } from "../lib/t";

/** A rate with its 95% interval and n. The bar is decoration; every value is also written out (REQ-WEB-A11Y.1). */
export function RateCell({ label, rate }: { label: string; rate: Rate }) {
  const known = rate.rate !== null && rate.lo !== null && rate.hi !== null;
  return (
    <div className="rate-cell">
      <p className="rate-label">{label}</p>
      {known ? (
        <>
          <p className="rate-value">{pct(rate.rate)}</p>
          <svg className="rate-bar" viewBox="0 0 100 10" aria-hidden="true" focusable="false" preserveAspectRatio="none">
            <rect x="0" y="4" width="100" height="2" className="rate-track" />
            <rect x={(rate.lo as number) * 100} y="2" width={Math.max(0.6, ((rate.hi as number) - (rate.lo as number)) * 100)} height="6" className="rate-interval" />
            <rect x={(rate.rate as number) * 100 - 0.6} y="0" width="1.2" height="10" className="rate-point" />
          </svg>
          <p className="rate-interval-text">{t("score.interval", { lo: pct(rate.lo), hi: pct(rate.hi) })}</p>
        </>
      ) : (
        <p className="rate-value">{t("score.not_enough")}</p>
      )}
      <p className="rate-n">{t("score.n", { n: rate.n })}</p>
    </div>
  );
}
