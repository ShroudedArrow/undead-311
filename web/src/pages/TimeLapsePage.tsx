import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { PanelError } from "../components/PanelError";
import { useData } from "../lib/data";
import { formatDay } from "../lib/format";
import { usePrefersReducedMotion } from "../lib/motion";
import { parsePoints } from "../lib/parse";
import { pointsToRows } from "../lib/points";
import { buildTimeline, DAY_MS, DURATION_S, timeAt, visibleAt, yearCounts } from "../lib/timelapse";
import { t } from "../lib/t";

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

  const start = timeline?.[0]?.t ?? 0;
  const end = timeline?.[timeline.length - 1]?.t ?? 0;
  const [progress, setProgress] = useState(1); // 1 = everything shown until play is pressed
  const [playing, setPlaying] = useState(false);
  const [played, setPlayed] = useState(false);
  const raf = useRef(0);
  const progressRef = useRef(1);
  const last = useRef(0);
  const duration = Math.min(DURATION_S, Math.max(4, (end - start) / DAY_MS / 120));

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

  const now = timeline ? timeAt(start, end, progress) : 0;
  const shown = useMemo(() => (timeline ? visibleAt(timeline, now) : []), [timeline, now]);
  const years = useMemo(() => (timeline ? yearCounts(timeline) : []), [timeline]);
  const play = () => { progressRef.current = 0; setProgress(0); setPlayed(true); setPlaying(true); };
  const ready = timeline !== null && timeline.length > 0;

  return (
    <div className="page timelapse-page">
      <h1>{t("timelapse.title")}</h1>
      {(points.status === "error") && <PanelError file={points.file} error={points.error} />}
      {timeline && !ready && <p data-testid="timelapse-empty">{t("timelapse.empty")}</p>}
      {ready && (
        <>
          <p>{t("timelapse.intro", { from: formatDay(iso(start)), to: formatDay(iso(end)) })}</p>
          {reduced ? <p data-testid="reduced-note">{t("timelapse.reduced_note")}</p> : (
            <div className="timelapse-controls" role="group" aria-label={t("timelapse.title")}>
              {playing ? (
                <button type="button" onClick={stop}>{t("timelapse.pause")}</button>
              ) : played && progress < 1 ? (
                <button type="button" onClick={() => setPlaying(true)}>{t("timelapse.resume")}</button>
              ) : (
                <button type="button" onClick={play}>{played ? t("timelapse.restart") : t("timelapse.play")}</button>
              )}
              <button type="button" onClick={() => { stop(); progressRef.current = 1; setProgress(1); }} disabled={progress >= 1 && !playing}>{t("timelapse.skip")}</button>
              <label>
                {t("timelapse.scrub")}
                <input type="range" min={0} max={1000} value={Math.round(progress * 1000)} aria-valuetext={formatDay(iso(now))} onChange={(e) => { stop(); const v = Number(e.target.value) / 1000; progressRef.current = v; setProgress(v); }} />
              </label>
            </div>
          )}
          <p role="status" aria-live={playing ? "off" : "polite"} data-testid="timelapse-now">{t("timelapse.now", { date: formatDay(iso(now)), count: shown.length, total: timeline.length })}</p>
          <div className="timelapse-map">
            <Suspense fallback={<p>{t("map.loading")}</p>}>
              <MapView rows={shown} selectedId={null} onSelect={() => undefined} />
            </Suspense>
          </div>
          <h2>{t("timelapse.summary_heading")}</h2>
          <div className="table-wrap" tabIndex={0} role="region" aria-label={t("timelapse.caption")}>
            <table className="zombie-table" data-testid="year-table">
              <caption>{t("timelapse.caption")}</caption>
              <thead><tr><th scope="col">{t("timelapse.col_year")}</th><th scope="col">{t("timelapse.col_count")}</th><th scope="col">{t("timelapse.col_total")}</th></tr></thead>
              <tbody>{years.map((y) => <tr key={y.year}><th scope="row">{y.year}</th><td>{y.count}</td><td>{y.total}</td></tr>)}</tbody>
            </table>
          </div>
          <p className="count-note">{t("timelapse.floor")}</p>
        </>
      )}
    </div>
  );
}
