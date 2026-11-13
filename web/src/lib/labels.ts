import { UNKNOWN } from "./filter";
import { t } from "./t";

/** Display label for a filter option or table cell. Unknown keys fall back to the raw value. */
export function familyLabel(key: string): string {
  const s = t(`families.${key}`);
  return s === `families.${key}` ? key : s;
}

export function groupLabel(by: "neighborhood" | "department" | "family" | "year", key: string): string {
  if (key === UNKNOWN) return t("filters.unknown");
  return by === "family" ? familyLabel(key) : key;
}
