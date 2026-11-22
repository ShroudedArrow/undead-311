import { lazy, Suspense, useEffect, useId, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { PageHeader } from "../components/PageHeader";
import { PanelError } from "../components/PanelError";
import { ShowMore } from "../components/ShowMore";
import { decodeShown, PAGE_SIZE, writeShown } from "../lib/paging";
import { useData } from "../lib/data";
import { familyLabel } from "../lib/labels";
import { methodsPageSettings } from "../lib/sensitivityNote";
import { parsePoints, parseSensitivityGrid } from "../lib/parse";
import { pointsToRows } from "../lib/points";
import { boundsOf, nearStreet, searchStreets, type StreetIndex } from "../lib/streets";
import { t } from "../lib/t";
import { decodeStreetState, encodeStreetState, STREET_RADII_M } from "../lib/url";

const MapView = lazy(() => import("../map/MapView"));

/** Search distances offered, in meters; "widen" steps to the next one. */
const RADII_M = STREET_RADII_M;

/**
 * "Check my street" (REQ-WEB-STREET.1): search a client-side street index (no API), zoom to the street and list the nearby
 * possible zombies. The empty state invites a wider search and points at the 90-day window. The chosen street and distance
 * live in the URL (`s`, `r`), so the result can be shared (REQ-WEB-LINKS.1).
 */
export default function StreetPage() {
  const [params, setParams] = useSearchParams();
  const [index, setIndex] = useState<StreetIndex | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [query, setQuery] = useState(params.get("q") ?? "");
  const points = useData("points.json", parsePoints);
  const grid = useData("sensitivity_grid.json", parseSensitivityGrid);
  const inputId = useId();
  const listId = useId();

  useEffect(() => {
    let live = true;
    import("../generated/streets.json")
      .then((m) => live && setIndex((m.default ?? m) as StreetIndex))
      .catch((e: unknown) => live && setLoadError(e instanceof Error ? e.message : "request failed"));
    return () => {
      live = false;
    };
  }, []);

  const { key: chosenKey, radius } = decodeStreetState(params.toString());
  const radiusIdx = RADII_M.indexOf(radius as (typeof RADII_M)[number]);
  const chosen = useMemo(() => index?.streets.find((e) => e.k === chosenKey) ?? null, [index, chosenKey]);
  const matches = useMemo(() => (index && query.trim() ? searchStreets(index, query) : []), [index, query]);
  const rows = useMemo(() => (points.status === "ok" ? pointsToRows(points.data).filter((r) => r.tier === "headline") : []), [points]);
  const near = useMemo(() => (chosen ? nearStreet(chosen, rows, radius) : []), [chosen, rows, radius]);
  const bounds = useMemo(() => (chosen ? boundsOf(chosen) : null), [chosen]);
  const note = grid.status === "ok" ? methodsPageSettings(grid.data) : null;

  const shown = decodeShown(params);
  const showMore = () => setParams(writeShown(new URLSearchParams(params), shown + PAGE_SIZE), { replace: true });
  const choose = (key: string, r: number = radius) => setParams(encodeStreetState({ key, radius: r }), { replace: false });

  return (
    <div className="page street-page form-sheet">
      <PageHeader title={t("street.title")} />
      <p>{t("street.intro")}</p>
      {loadError && <PanelError file="streets.json" error={loadError} />}
      {!index && !loadError && <p>{t("street.loading")}</p>}
      {index && (
        <>
          <div className="street-search">
            <label htmlFor={inputId}>{t("street.label")}</label>
            <input id={inputId} type="search" value={query} placeholder={t("street.placeholder")} autoComplete="off" aria-controls={listId} onChange={(e) => setQuery(e.target.value)} />
            <ul id={listId} className="street-results" aria-label={t("street.results_label")}>
              {matches.map((m) => (
                <li key={m.k}>
                  <button type="button" onClick={() => { setQuery(m.n); choose(m.k); }} aria-pressed={m.k === chosenKey}>{m.n}</button>
                </li>
              ))}
            </ul>
            {query.trim() && matches.length === 0 && <p data-testid="street-no-match">{t("street.no_match")}</p>}
            {index.source === "cases" && <p className="count-note">{t("street.source_cases")}</p>}
          </div>
          {!chosen && !query.trim() && <p>{t("street.pick")}</p>}
        </>
      )}
      {chosen && (
        <section aria-labelledby="near-h" data-testid="street-result">
          <h2 id="near-h">{t("street.near_heading", { meters: radius, street: chosen.n })}</h2>
          {points.status === "error" && <PanelError file={points.file} error={points.error} />}
          {points.status === "ok" && (
            <>
              <div className="street-map">
                <Suspense fallback={<p>{t("map.loading")}</p>}>
                  <MapView rows={near.map((x) => x.item)} selectedId={null} onSelect={() => undefined} bounds={bounds} />
                </Suspense>
              </div>
              {near.length > 0 ? (
                <>
                  <p data-testid="street-count">{t("street.near_count", { count: near.length })}</p>
                  <ul className="street-near plain-list">
                    {near.slice(0, shown).map(({ item, meters }) => (
                      <li key={item.id}>
                        <Link to={`/zombie/${encodeURIComponent(item.id)}`}>
                          {familyLabel(item.family)}, {item.neighborhood ?? t("filters.unknown_neighborhood")}, {item.year}
                        </Link>{" "}
                        <span className="count-note">{t("street.away", { meters: Math.round(meters) })}</span>
                      </li>
                    ))}
                  </ul>
                  <ShowMore shown={shown} total={near.length} onMore={showMore} />
                </>
              ) : (
                <div data-testid="street-empty">
                  <p>{t("empty.no_zombies_block")}</p>
                  {note && <p className="count-note">{t("street.grid_90", note)}</p>}
                  <p><Link to="/methods">{t("street.grid_link")}</Link></p>
                </div>
              )}
              {radiusIdx < RADII_M.length - 1 ? (
                <button type="button" className="street-widen" onClick={() => choose(chosen.k, RADII_M[radiusIdx + 1])}>
                  {t("street.widen", { meters: RADII_M[radiusIdx + 1] })}
                </button>
              ) : (
                <p className="count-note">{t("street.widest")}</p>
              )}
            </>
          )}
        </section>
      )}
    </div>
  );
}
