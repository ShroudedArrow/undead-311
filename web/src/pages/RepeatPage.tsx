import { lazy, Suspense, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { PanelError } from "../components/PanelError";
import { useData } from "../lib/data";
import { familyLabel } from "../lib/labels";
import { parseRepeatOffenders, parseZombies } from "../lib/parse";
import { chainRows, firstZombieOfChain, REPEAT_MIN_HEADLINE, sortChains } from "../lib/repeat";
import { t } from "../lib/t";

const MapView = lazy(() => import("../map/MapView"));

/** Repeat offenders: the chains the engine exports, with a map of where they are (REQ-WEB-REPEAT.1). */
export default function RepeatPage() {
  const data = useData("repeat_offenders.json", parseRepeatOffenders);
  const zombies = useData("zombies.json", parseZombies);
  const [picked, setPicked] = useState<string | null>(null);
  const chains = useMemo(() => (data.status === "ok" ? sortChains(data.data.repeat_offenders) : []), [data]);
  const rows = useMemo(() => chainRows(chains), [chains]);
  const zs = zombies.status === "ok" ? zombies.data.zombies : [];
  return (
    <div className="page repeat-page">
      <h1>{t("repeat.title")}</h1>
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
                  <th scope="col">{t("repeat.col_where")}</th>
                  <th scope="col">{t("repeat.col_type")}</th>
                  <th scope="col">{t("repeat.col_times")}</th>
                  <th scope="col">{t("repeat.col_headline")}</th>
                  <th scope="col">{t("repeat.col_privacy")}</th>
                  <th scope="col">{t("repeat.col_open")}</th>
                </tr>
              </thead>
              <tbody>
                {chains.map((c) => {
                  const first = firstZombieOfChain(c.chain_id, zs);
                  return (
                    <tr key={c.chain_id} data-chain={c.chain_id} aria-current={c.chain_id === picked ? "true" : undefined} className={c.chain_id === picked ? "row-picked" : undefined}>
                      <th scope="row">{c.neighborhood ?? t("filters.unknown_neighborhood")}</th>
                      <td>{c.type_family ? familyLabel(c.type_family) : t("filters.unknown")}</td>
                      <td>{c.times_risen}</td>
                      <td>{c.headline_count}</td>
                      <td>{c.block_level ? t("repeat.block_level") : t("repeat.exact")}</td>
                      <td>{first ? <Link to={`/zombie/${encodeURIComponent(first.zombie_id)}`}>{t("repeat.chain_open")}</Link> : null}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      ))}
    </div>
  );
}
