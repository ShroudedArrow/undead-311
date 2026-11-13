import { UNKNOWN } from "./filter";
import { t } from "./t";

/** Display label for a filter option or table cell. Unknown keys fall back to the raw value. */
export function familyLabel(key: string): string {
  const s = t(`families.${key}`);
  return s === `families.${key}` ? key : s;
}

/** Readable department name from en.json, with the code in parentheses (UX-8). Unlisted codes show as they are. */
export function departmentLabel(key: string): string {
  const s = t(`departments.${key}`);
  return s === `departments.${key}` ? key : s;
}

export function groupLabel(by: "neighborhood" | "department" | "family" | "year", key: string): string {
  if (key === UNKNOWN) return t("filters.unknown");
  if (by === "department") return departmentLabel(key);
  return by === "family" ? familyLabel(key) : key;
}
