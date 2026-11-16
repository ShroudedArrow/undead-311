import { lazy, Suspense, useId, useMemo, useState } from "react";
import { Outlet, useMatch, useNavigate, useSearchParams } from "react-router-dom";
import { CountLine } from "../components/CountLine";
import { Filters } from "../components/Filters";
import { CopyLink, NeighborhoodShareLink } from "../components/ShareLinks";
import { PanelError } from "../components/PanelError";
import { ZombieTable } from "../components/ZombieTable";
import { visibleSet } from "../lib/filter";
import { shardKey } from "../lib/shard";
import { useZombieShards, usePoints } from "../lib/shards";
import { pointsToRows } from "../lib/points";
import { buildTableRows, bulkIds } from "../lib/table";
import { t } from "../lib/t";
import { decodeState, encodeState, type PageState } from "../lib/url";

const MapView = lazy(() => import("../map/MapView"));

/** Map page: filters, count and the map, over one shared visible set (REQ-WEB-MAP.2-4). The card opens as a nested route. */
export default function HomePage() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const match = useMatch("/zombie/:id");
  const selectedId = match?.params.id ? decodeURIComponent(match.params.id) : null;
  const state = useMemo(() => decodeState(params.toString()), [params]);
  const pointsState = usePoints(state.tierMode === "all"); // the first view reads the headline tier only; the others load when switched on
  const points = pointsState.load;
  const rows = useMemo(() => (points.status === "ok" ? pointsToRows(points.data) : []), [points]);
  const visible = useMemo(() => visibleSet(rows, state.filters, state.tierMode), [rows, state]);
  // zombie records load per shard, and only the shards the visible rows fall in (table view, bulk layer)
  const shardKeys = useMemo(
    () => (state.view === "table" || state.bulk ? visible.items.map((r) => shardKey(r.neighborhood, r.year)) : null),
    [state.view, state.bulk, visible],
  );
  const zombies = useZombieShards(shardKeys);
  const zombieById = useMemo(() => (zombies.status === "ok" ? new Map(zombies.data.zombies.map((z) => [z.zombie_id, z])) : null), [zombies]);

  const bulkSet = useMemo(() => (state.bulk ? bulkIds(visible.items, zombieById) : null), [state.bulk, visible, zombieById]);
  // filter menus count what the current tier mode can show, so an option's number matches what picking it yields
  const optionRows = useMemo(() => (state.tierMode === "all" ? rows : rows.filter((r) => r.tier === "headline")), [rows, state.tierMode]);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const filtersId = useId();
  const tierNoteId = useId();
  const bulkNoteId = useId();
  const update = (next: PageState) => setParams(encodeState(next), { replace: true });
  const select = (id: string) => navigate({ pathname: `/zombie/${encodeURIComponent(id)}`, search: params.toString() });

  return (
    <div className="home">
      <aside className="filters-panel">
        <h1>{t("app.title")}</h1>
        <div className="hero-text">
          <p className="tagline">{t("app.hero_line")}</p>
          <p className="tagline">{t("app.hero_subtitle")}</p>
        </div>
        {points.status === "error" && <PanelError file={points.file} error={points.error} />}
        {pointsState.extraError && <PanelError file={pointsState.extraError.file} error={pointsState.extraError.error} />}
        {pointsState.pending && <p role="status">{t("filters.loading")}</p>}
        {points.status === "loading" && <p>{t("filters.loading")}</p>}
        {points.status === "ok" && (
          <>
            <CountLine headlineCount={visible.headlineCount} allCount={state.tierMode === "all" ? visible.allCount : undefined} />
            <button type="button" className="filters-toggle" aria-expanded={filtersOpen} aria-controls={filtersId} onClick={() => setFiltersOpen(!filtersOpen)}>
              {t(filtersOpen ? "filters.hide" : "filters.show")}
            </button>
            <div id={filtersId} className={filtersOpen ? "filters-body filters-open" : "filters-body"}>
              <label className="tier-toggle">
                <input
                  type="checkbox"
                  checked={state.tierMode === "all"}
                  aria-describedby={tierNoteId}
                  onChange={(e) => update({ ...state, tierMode: e.target.checked ? "all" : "headline" })}
                />
                <span>{t("filters.tier_toggle")}</span>
              </label>
              <p className="count-note" id={tierNoteId}>
                {t("filters.tier_toggle_note")}
              </p>
              <label className="tier-toggle">
                <input type="checkbox" checked={state.bulk} aria-describedby={bulkNoteId} onChange={(e) => update({ ...state, bulk: e.target.checked })} />
                <span>{t("filters.bulk_toggle")}</span>
              </label>
              <p className="count-note" id={bulkNoteId} data-testid="bulk-note">
                {state.bulk && bulkSet && zombies.status === "ok" ? (bulkSet.size === 0 ? t("filters.bulk_none") : t("filters.bulk_count", { count: bulkSet.size })) : t("filters.bulk_note")}
              </p>
              <p className="filters-share">
                <CopyLink />
                {state.filters.neighborhoods.length === 1 ? <NeighborhoodShareLink name={state.filters.neighborhoods[0]} /> : null}
              </p>
              <Filters rows={optionRows} filters={state.filters} onChange={(filters) => update({ ...state, filters })} />
            </div>
          </>
        )}
      </aside>
      <section className="stage">
        <div className="view-switch" role="group" aria-label={t("map.view_switch")}>
          <button type="button" aria-pressed={state.view === "map"} onClick={() => update({ ...state, view: "map" })}>
            {t("nav.map_view")}
          </button>
          <button type="button" aria-pressed={state.view === "table"} onClick={() => update({ ...state, view: "table" })}>
            {t("nav.table")}
          </button>
        </div>
        {state.view === "map" ? (
          <Suspense fallback={<p>{t("map.loading")}</p>}>
            <MapView rows={visible.items} selectedId={selectedId} onSelect={select} bulkIds={bulkSet} />
          </Suspense>
        ) : (
          <>
            {zombies.status === "error" && <PanelError file={zombies.file} error={zombies.error} />}
            <ZombieTable rows={buildTableRows(visible.items, zombieById, state.bulk)} search={params.toString()} />
          </>
        )}
      </section>
      <Outlet />
    </div>
  );
}
