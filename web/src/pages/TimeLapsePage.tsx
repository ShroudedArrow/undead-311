import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { PanelError } from "../components/PanelError";
import { useData } from "../lib/data";
import { formatDay } from "../lib/format";
import { usePrefersReducedMotion } from "../lib/motion";
import { parsePoints } from "../lib/parse";
import { pointsToRows } from "../lib/points";
import { buildTimeline, DAY_MS, DURATION_S, durationFor, focusTimeline, SPEEDS, timeAt, TRAIL_MONTHS, visibleTrail, yearCounts, yearsIn } from "../lib/timelapse";
import { familyLabel } from "../lib/labels";
import { t } from "../lib/t";
import { MapLegend } from "../components/MapLegend";
import { FAMILY_ORDER } from "../map/sprites";

const MapView = lazy(() => import("../map/MapView"));
const iso = (ms: number) => new Date(ms).toISOString().slice(0, 10);

/**
 * Night of the Living 311 (REQ-WEB-TIMELAPSE.1): possible zombies appear across Boston on the day they were reported again.
 * It starts only when the visitor presses play, can be skipped to the end or scrubbed, and under reduced motion it does not
 * animate at all: the page shows every possible zombie and a table of counts per year.
 */
export default function TimeLapsePage() {
  const points = useData("points.json", parsePoints);
  const reduced = usePrefersReducedMotion();
  const timeline = useMemo(() => {
    if (points.status !== "ok") return null;
    const { id, date } = points.data;
    const dates = new Map(id.map((x, i) => [x, date?.[i] ?? ""]));
    return buildTimeline(pointsToRows(points.data), dates);
  }, [points]);

  // The focus: what the visitor narrowed the view to. Year range defaults to every year, so "no limit" needs no extra state.
  const years = useMemo(() => (timeline ? yearsIn(timeline) : []), [timeline]);
  const families = useMemo(() => (timeline ? FAMILY_ORDER.filter((f) => timeline.some((d) => d.row.family === f)) : []), [timeline]);
  const neighborhoods = useMemo(() => (timeline ? [...new Set(timeline.map((d) => d.row.neighborhood).filter((n): n is string => !!n))].sort() : []), [timeline]);
  const [family, setFamily] = useState<string | null>(null);
  const [neighborhood, setNeighborhood] = useState<string | null>(null);
  const [yearRange, setYearRange] = useState<[number, number] | null>(null);
  const [speed, setSpeed] = useState<number>(1);
  const [trail, setTrail] = useState<number | null>(null);
  const range: [number, number] = yearRange ?? [years[0] ?? 0, years[years.length - 1] ?? 0];
  const focused = useMemo(
    () => (timeline ? focusTimeline(timeline, { family, neighborhood, fromYear: range[0], toYear: range[1] }) : []),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [timeline, family, neighborhood, range[0], range[1]],
  );

  const start = focused[0]?.t ?? 0;
  const end = focused[focused.length - 1]?.t ?? 0;
  const [progress, setProgress] = useState(1); // 1 = everything shown until play is pressed
  const [playing, setPlaying] = useState(false);
  const [played, setPlayed] = useState(false);
  const raf = useRef(0);
  const progressRef = useRef(1);
  const last = useRef(0);
  const duration = durationFor(Math.min(DURATION_S, Math.max(4, (end - start) / DAY_MS / 120)), speed);

  const stop = useCallback(() => {
    cancelAnimationFrame(raf.current);
    setPlaying(false);
  }, []);

  useEffect(() => {
    if (!playing) return;
    last.current = performance.now();
    let p = progressRef.current;
    const step = (now: number) => {
      const dt = (now - last.current) / 1000;
      last.current = now;
      p = Math.min(1, p + dt / duration);
      progressRef.current = p;
      setProgress(p);
      if (p >= 1) setPlaying(false);
      else raf.current = requestAnimationFrame(step);
    };
    raf.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf.current);
  }, [playing, duration]);

  useEffect(() => { if (reduced) stop(); }, [reduced, stop]);
  useEffect(() => {
    if (!playing) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") { stop(); progressRef.current = 1; setProgress(1); } };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [playing, stop]);

  const now = timeAt(start, end, progress);
  const shown = useMemo(() => visibleTrail(focused, now, trail), [focused, now, trail]);
  const perYear = useMemo(() => yearCounts(focused), [focused]);
  // a new focus starts from the whole view: stop the clock and show everything in it
  const refocus = (apply: () => void) => {
    stop();
    progressRef.current = 1;
    setProgress(1);
    apply();
  };
  const play = () => { progressRef.current = 0; setProgress(0); setPlayed(true); setPlaying(true); };
  const ready = timeline !== null && timeline.length > 0;

  return (
    <div className="page timelapse-page">
      <h1>{t("timelapse.title")}</h1>
      {(points.status === "error") && <PanelError file={points.file} error={points.error} />}
      {points.status === "loading" && <div data-slot="page-loading" aria-busy="true"><p className="count-note">{t("app.loading_section")}</p></div>}
      {timeline && !ready && <p data-testid="timelapse-empty">{t("timelapse.empty")}</p>}
      {ready && (
        <>
          <p>{t("timelapse.intro", { from: formatDay(iso(focused.length ? start : timeline[0].t)), to: formatDay(iso(focused.length ? end : timeline[timeline.length - 1].t)) })}</p>
          <div className="timelapse-bar">
            {reduced ? <p data-testid="reduced-note">{t("timelapse.reduced_note")}</p> : (
              <div className="timelapse-controls" role="group" aria-label={t("timelapse.title")}>
                {playing ? (
                  <button type="button" onClick={stop}>{t("timelapse.pause")}</button>
                ) : played && progress < 1 ? (
                  <button type="button" onClick={() => setPlaying(true)}>{t("timelapse.resume")}</button>
                ) : (
                  <button type="button" onClick={play} disabled={focused.length === 0}>{played ? t("timelapse.restart") : t("timelapse.play")}</button>
                )}
                <button type="button" onClick={() => { stop(); progressRef.current = 1; setProgress(1); }} disabled={progress >= 1 && !playing}>{t("timelapse.skip")}</button>
                <label className="timelapse-scrub">
                  {t("timelapse.scrub")}
                  <input type="range" min={0} max={1000} value={Math.round(progress * 1000)} disabled={focused.length === 0} aria-valuetext={formatDay(iso(now))} onChange={(e) => { stop(); const v = Number(e.target.value) / 1000; progressRef.current = v; setProgress(v); }} />
                </label>
              </div>
            )}
            <fieldset className="timelapse-focus">
              <legend>{t("timelapse.controls_heading")}</legend>
              <label>
                {t("timelapse.family")}
                <select value={family ?? ""} onChange={(e) => refocus(() => setFamily(e.target.value || null))}>
                  <option value="">{t("timelapse.all_families")}</option>
                  {families.map((f) => <option key={f} value={f}>{familyLabel(f)}</option>)}
                </select>
              </label>
              <label>
                {t("timelapse.neighborhood")}
                <select value={neighborhood ?? ""} onChange={(e) => refocus(() => setNeighborhood(e.target.value || null))}>
                  <option value="">{t("timelapse.all_neighborhoods")}</option>
                  {neighborhoods.map((n) => <option key={n} value={n}>{n}</option>)}
                </select>
              </label>
              <label>
                {t("timelapse.year_from")}
                <select value={range[0]} onChange={(e) => refocus(() => { const v = Number(e.target.value); setYearRange([v, Math.max(v, range[1])]); })}>
                  {years.map((y) => <option key={y} value={y}>{y}</option>)}
                </select>
              </label>
              <label>
                {t("timelapse.year_to")}
                <select value={range[1]} onChange={(e) => refocus(() => { const v = Number(e.target.value); setYearRange([Math.min(v, range[0]), v]); })}>
                  {years.map((y) => <option key={y} value={y}>{y}</option>)}
                </select>
              </label>
              <label>
                {t("timelapse.trail")}
                <select value={trail ?? ""} aria-describedby="trail-note" onChange={(e) => setTrail(e.target.value ? Number(e.target.value) : null)}>
                  <option value="">{t("timelapse.trail_all")}</option>
                  {TRAIL_MONTHS.map((m) => <option key={m} value={m}>{t("timelapse.trail_months", { count: m })}</option>)}
                </select>
              </label>
              {reduced ? null : (
                <label>
                  {t("timelapse.speed")}
                  <select value={speed} onChange={(e) => setSpeed(Number(e.target.value))}>
                    {SPEEDS.map((v) => <option key={v} value={v}>{t("timelapse.speed_option", { speed: v })}</option>)}
                  </select>
                </label>
              )}
            </fieldset>
            <p className="count-note" id="trail-note">{t("timelapse.trail_note")}</p>
          </div>
          <p role="status" aria-live={playing ? "off" : "polite"} data-testid="timelapse-now">
            {focused.length === 0
              ? t("timelapse.no_match")
              : trail === null
                ? t("timelapse.now", { date: formatDay(iso(now)), count: shown.length, total: focused.length })
                : t("timelapse.now_trail", { date: formatDay(iso(now)), count: shown.length, months: trail, total: focused.length })}
          </p>
          <div className="timelapse-map">
            <Suspense fallback={<p>{t("map.loading")}</p>}>
              <MapView rows={shown} selectedId={null} onSelect={() => undefined} />
            </Suspense>
            <MapLegend showOutline={false} />
          </div>
          <h2>{t("timelapse.summary_heading")}</h2>
          <div className="table-wrap" tabIndex={0} role="region" aria-label={t("timelapse.caption")}>
            <table className="zombie-table" data-testid="year-table">
              <caption>{t("timelapse.caption")}</caption>
              <thead><tr><th scope="col">{t("timelapse.col_year")}</th><th scope="col">{t("timelapse.col_count")}</th><th scope="col">{t("timelapse.col_total")}</th></tr></thead>
              <tbody>{perYear.map((y) => <tr key={y.year}><th scope="row">{y.year}</th><td>{y.count}</td><td>{y.total}</td></tr>)}</tbody>
            </table>
          </div>
          <p className="count-note">{t("timelapse.floor")}</p>
        </>
      )}
    </div>
  );
}
