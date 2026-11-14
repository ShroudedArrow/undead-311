import { UNKNOWN } from "./filter";
import { t } from "./t";

/** Display label for a filter option or table cell. Unknown keys fall back to the raw value. */
export function familyLabel(key: string): string {
  const s = t(`families.${key}`);
  return s === `families.${key}` ? key : s;
}

/**
 * One key per department (UX-11, ops#24): the legacy system writes a code (PWDx) and the new system writes a name
 * (Public Works Department (PWD)). Names listed in en.json `department_aliases` map to the code, so a filter covers both systems.
 */
export function canonicalDepartment<T extends string | null>(raw: T): T | string {
  if (raw === null) return raw;
  const key = `department_aliases.${raw}`;
  const s = t(key);
  return s === key ? raw : s;
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
