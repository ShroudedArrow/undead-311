import { lazy, Suspense, useMemo } from "react";
import { Outlet, useMatch, useNavigate, useSearchParams } from "react-router-dom";
import { CountLine } from "../components/CountLine";
import { Filters } from "../components/Filters";
import { PanelError } from "../components/PanelError";
import { ZombieTable } from "../components/ZombieTable";
import { visibleSet } from "../lib/filter";
import { useData } from "../lib/data";
import { parsePoints, parseZombies } from "../lib/parse";
import { pointsToRows } from "../lib/points";
import { buildTableRows } from "../lib/table";
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
  const points = useData("points.json", parsePoints);
  const rows = useMemo(() => (points.status === "ok" ? pointsToRows(points.data) : []), [points]);
  const zombies = useData(state.view === "table" ? "zombies.json" : null, parseZombies);
  const zombieById = useMemo(() => (zombies.status === "ok" ? new Map(zombies.data.zombies.map((z) => [z.zombie_id, z])) : null), [zombies]);
  const visible = useMemo(() => visibleSet(rows, state.filters, state.tierMode), [rows, state]);

  const update = (next: PageState) => setParams(encodeState(next), { replace: true });
  const select = (id: string) => navigate({ pathname: `/zombie/${encodeURIComponent(id)}`, search: params.toString() });

  return (
    <div className="home">
      <aside className="filters-panel">
        <h1>{t("app.title")}</h1>
        <p className="tagline">{t("app.hero_line")}</p>
        <p className="tagline">{t("app.hero_subtitle")}</p>
        {points.status === "error" && <PanelError file={points.file} error={points.error} />}
        {points.status === "loading" && <p>{t("filters.loading")}</p>}
        {points.status === "ok" && (
          <>
            <CountLine count={visible.headlineCount} />
            <Filters rows={rows} filters={state.filters} onChange={(filters) => update({ ...state, filters })} />
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
            <MapView rows={visible.items} selectedId={selectedId} onSelect={select} />
          </Suspense>
        ) : (
          <>
            {zombies.status === "error" && <PanelError file={zombies.file} error={zombies.error} />}
            <ZombieTable rows={buildTableRows(visible.items, zombieById)} search={params.toString()} />
          </>
        )}
      </section>
      <Outlet />
    </div>
  );
}
