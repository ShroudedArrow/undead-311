import { aggregate, options, type Filters as FilterState, type FilterableZombie, type GroupBy } from "../lib/filter";
import { groupLabel } from "../lib/labels";
import { t } from "../lib/t";

type Dim = { by: GroupBy; field: keyof FilterState; label: string };

const DIMS: Dim[] = [
  { by: "neighborhood", field: "neighborhoods", label: "filters.neighborhood" },
  { by: "department", field: "departments", label: "filters.department" },
  { by: "family", field: "families", label: "filters.family" },
  { by: "year", field: "years", label: "filters.year" },
];

interface Props {
  /** All rows, unfiltered, so every option stays visible. */
  rows: readonly FilterableZombie[];
  filters: FilterState;
  onChange: (next: FilterState) => void;
}

/** Filter menus for neighborhood, department, case type and year (REQ-WEB-MAP.2). Each menu is a keyboard-operable checkbox list. */
export function Filters({ rows, filters, onChange }: Props) {
  const any = DIMS.some((d) => filters[d.field].length > 0);
  return (
    <form aria-label={t("filters.heading")} onSubmit={(e) => e.preventDefault()}>
      {DIMS.map(({ by, field, label }) => {
        const selected = filters[field] as (string | number)[];
        const counts = new Map(aggregate(rows, by).map((c) => [c.key, c.count]));
        return (
          <details className="filter-group" key={field}>
            <summary>
              {t(label)}
              {selected.length > 0 ? ` (${t("filters.selected", { count: selected.length })})` : ""}
            </summary>
            <ul>
              {options(rows, by).map((key) => {
                const value = by === "year" ? Number(key) : key;
                const checked = selected.includes(value);
                return (
                  <li key={key}>
                    <label>
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => {
                          const next = checked ? selected.filter((v) => v !== value) : [...selected, value];
                          onChange({ ...filters, [field]: next });
                        }}
                      />
                      <span>
                        {groupLabel(by, key)} ({counts.get(key) ?? 0})
                      </span>
                    </label>
                  </li>
                );
              })}
            </ul>
          </details>
        );
      })}
      <button type="button" disabled={!any} onClick={() => onChange({ neighborhoods: [], departments: [], families: [], years: [] })}>
        {t("filters.clear")}
      </button>
    </form>
  );
}
