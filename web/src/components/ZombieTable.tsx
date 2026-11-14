import { useState } from "react";
import { Link } from "react-router-dom";
import { formatGap } from "../lib/format";
import { familyLabel } from "../lib/labels";
import { sortRows, type SortDir, type SortKey, type TableRow } from "../lib/table";
import { t } from "../lib/t";

const COLUMNS: { key: SortKey; label: string }[] = [
  { key: "date", label: "table.col_date" },
  { key: "gap", label: "table.col_gap" },
  { key: "neighborhood", label: "table.col_neighborhood" },
  { key: "family", label: "table.col_family" },
  { key: "confidence", label: "table.col_confidence" },
];

/** Sortable table of the same possible zombies the map shows. Each row opens the autopsy card (REQ-WEB-TABLE.1). */
export function ZombieTable({ rows, search }: { rows: readonly TableRow[]; search: string }) {
  const [key, setKey] = useState<SortKey>("date");
  const [dir, setDir] = useState<SortDir>("desc");
  const sorted = sortRows(rows, key, dir);
  if (rows.length === 0) return <p className="table-empty">{t("empty.no_matches")}</p>;
  return (
    <div className="table-wrap">
      <table className="zombie-table" data-testid="zombie-table">
        <caption>{t("table.caption")}</caption>
        <thead>
          <tr>
            {COLUMNS.map((c) => (
              <th key={c.key} scope="col" aria-sort={c.key === key ? (dir === "asc" ? "ascending" : "descending") : "none"}>
                <button
                  type="button"
                  onClick={() => {
                    if (c.key === key) setDir(dir === "asc" ? "desc" : "asc");
                    else {
                      setKey(c.key);
                      setDir("asc");
                    }
                  }}
                >
                  {t(c.label)}
                  {c.key === key ? ` (${t(dir === "asc" ? "table.sorted_asc" : "table.sorted_desc")})` : ""}
                </button>
              </th>
            ))}
            <th scope="col">{t("table.col_tier")}</th>
            <th scope="col">{t("table.col_open")}</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => (
            <tr key={r.id} data-id={r.id}>
              <td>{r.date}</td>
              <td>{r.gap === null ? "" : formatGap(r.gap)}</td>
              <td>{r.neighborhood || t("filters.unknown")}</td>
              <td>{familyLabel(r.family)}</td>
              <td>{r.confidence === null ? "" : r.confidence.toFixed(2)}</td>
              <td>{t(`tiers.${r.tier}`)}</td>
              <td>
                <Link to={{ pathname: `/zombie/${encodeURIComponent(r.id)}`, search }}>
                  {t("table.open_card", { id: r.id })}
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
