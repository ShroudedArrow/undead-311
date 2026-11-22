import { lazy, Suspense, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ShowMore } from "../components/ShowMore";
import { decodeShown, PAGE_SIZE, writeShown } from "../lib/paging";
import { PageHeader } from "../components/PageHeader";
import { PanelError } from "../components/PanelError";
import { useData } from "../lib/data";
import { familyLabel } from "../lib/labels";
import { parseRepeatOffenders } from "../lib/parse";
import { chainRows, decodeChainSort, REPEAT_MIN_HEADLINE, sortChains, sortChainsBy, type ChainSortKey } from "../lib/repeat";
import { t } from "../lib/t";

const MapView = lazy(() => import("../map/MapView"));

/** Repeat offenders: the chains the engine exports, with a map of where they are (REQ-WEB-REPEAT.1). */
export default function RepeatPage() {
  const data = useData("repeat_offenders.json", parseRepeatOffenders);
  const [picked, setPicked] = useState<string | null>(null);
  // Sort and rows shown live in the URL (`sort`, `dir`, `n`), so a link or a reload shows the same table.
  const [params, setParams] = useSearchParams();
  const { key: sortKey, dir } = decodeChainSort(params);
  const shown = decodeShown(params);
  const update = (mutate: (p: URLSearchParams) => void) => {
    const p = new URLSearchParams(params);
    mutate(p);
    setParams(p, { replace: true });
  };
  const chains = useMemo(() => (data.status === "ok" ? sortChains(data.data.repeat_offenders) : []), [data]);
  const ordered = useMemo(() => sortChainsBy(chains, sortKey, dir), [chains, sortKey, dir]);
  // the map always shows every chain; only the table is paged
  const rows = useMemo(() => chainRows(chains), [chains]);
  const sortBy = (key: ChainSortKey) =>
    update((p) => {
      const same = key === sortKey;
      const nextDir = same ? (dir === "asc" ? "desc" : "asc") : key === "where" || key === "type" ? "asc" : "desc";
      if (key === "times" && nextDir === "desc") {
        p.delete("sort");
        p.delete("dir");
      } else {
        p.set("sort", key);
        p.set("dir", nextDir);
      }
      writeShown(p, PAGE_SIZE);
    });
  const head = (key: ChainSortKey, label: string) => (
    <th scope="col" aria-sort={key === sortKey ? (dir === "asc" ? "ascending" : "descending") : "none"}>
      <button type="button" onClick={() => sortBy(key)}>
        {label}
        {key === sortKey ? ` (${t(dir === "asc" ? "table.sorted_asc" : "table.sorted_desc")})` : ""}
      </button>
    </th>
  );
  return (
    <div className="page repeat-page form-sheet">
      <PageHeader title={t("repeat.title")} />
      <p>{t("repeat.intro", { min: REPEAT_MIN_HEADLINE })}</p>
      {data.status === "loading" && <p>{t("filters.loading")}</p>}
      {data.status === "error" && <PanelError file={data.file} error={data.error} />}
      {data.status === "ok" && (chains.length === 0 ? (
        <p data-testid="repeat-empty">{t("repeat.empty", { min: REPEAT_MIN_HEADLINE })}</p>
      ) : (
        <>
          <p data-testid="repeat-count">{t("repeat.count", { count: chains.length })}</p>
          <div className="street-map">
            <Suspense fallback={<p>{t("map.loading")}</p>}>
              <MapView rows={rows} selectedId={picked} onSelect={setPicked} />
            </Suspense>
          </div>
          <div className="table-wrap" tabIndex={0} role="region" aria-label={t("repeat.caption")}>
            <table className="zombie-table" data-testid="repeat-table">
              <caption>{t("repeat.caption")}</caption>
              <thead>
                <tr>
                  {head("where", t("repeat.col_where"))}
                  {head("type", t("repeat.col_type"))}
                  {head("times", t("repeat.col_times"))}
                  {head("headline", t("repeat.col_headline"))}
                  <th scope="col">{t("repeat.col_privacy")}</th>
                  <th scope="col">{t("repeat.col_open")}</th>
                </tr>
              </thead>
              <tbody>
                {ordered.slice(0, shown).map((c) => {
                  const first = c.first_zombie_id ?? null;
                  return (
                    <tr key={c.chain_id} data-chain={c.chain_id} aria-current={c.chain_id === picked ? "true" : undefined} className={c.chain_id === picked ? "row-picked" : undefined}>
                      <th scope="row">{c.neighborhood ?? t("filters.unknown_neighborhood")}</th>
                      <td>{c.type_family ? familyLabel(c.type_family) : t("filters.unknown")}</td>
                      <td>{c.times_risen}</td>
                      <td>{c.headline_count}</td>
                      <td>{c.block_level ? t("repeat.block_level") : t("repeat.exact")}</td>
                      <td>{first ? (
                        <Link to={`/zombie/${encodeURIComponent(first)}`} aria-label={t("repeat.chain_open_label", { where: c.neighborhood ?? t("filters.unknown_neighborhood") })}>
                          {t("repeat.chain_open_short")}
                        </Link>
                      ) : null}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <ShowMore shown={shown} total={ordered.length} onMore={() => update((p) => writeShown(p, shown + PAGE_SIZE))} />
        </>
      ))}
    </div>
  );
}
