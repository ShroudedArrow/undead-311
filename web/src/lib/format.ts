import { t } from "./t";

/** Display formatting with a fixed locale and zone, so output never depends on the machine (REQ-WEB-CARD.1). */

const BOSTON = "America/New_York";

/** "Nov 13, 2026, 4:05 PM" in Boston time. Returns the input when it is not a date. */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat("en-US", { year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: BOSTON }).format(d);
}

/** "Nov 13, 2026" in Boston time. A bare date (YYYY-MM-DD) is shown as written, without a zone shift. */
export function formatDay(iso: string | null | undefined): string {
  if (!iso) return "";
  const bare = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  const d = bare ? new Date(Date.UTC(+bare[1], +bare[2] - 1, +bare[3], 12)) : new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat("en-US", { year: "numeric", month: "short", day: "numeric", timeZone: bare ? "UTC" : BOSTON }).format(d);
}

/** Days with one decimal; "1 day" when it rounds to one. */
export function roundDays(days: number): number {
  return Math.round(days * 10) / 10;
}

/**
 * Time between closure and re-report as words (REQ-WEB-CARD.1, UX-9). A gap of a day or more shows days with one decimal
 * (whole days without a decimal); under a day it shows hours, under an hour minutes, so "0 days" never appears.
 */
export function formatGap(days: number): string {
  const d = Math.max(0, days);
  const rounded = roundDays(d);
  if (rounded >= 1) return rounded === 1 ? t("card.day") : t("card.days", { days: rounded });
  const hours = Math.round(d * 24);
  if (hours >= 1) return hours === 1 ? t("card.hour") : t("card.hours", { n: hours });
  const minutes = Math.round(d * 1440);
  if (minutes >= 1) return minutes === 1 ? t("card.minute") : t("card.minutes", { n: minutes });
  return t("card.under_minute");
}
