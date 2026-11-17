import { useId, useMemo, useState } from "react";
import { useData } from "../lib/data";
import { parseExcess, parseSensitivityGrid } from "../lib/parse";
import { pct } from "../lib/rates";
import { defaultSetting, findPoint, MATCHINGS, radiusIsMinor, RADII, stepOf, WINDOWS, type Matching, type Setting } from "../lib/sensitivity";
import { excessShown, num1 } from "../lib/methods";
import { t } from "../lib/t";
import { PanelError } from "./PanelError";

/** "15, 30 and 50": the settings that were run, written out under a slider (REQ-WEB-SLIDERS.1, UX-42). */
const stopsText = (steps: readonly number[], and: string): string => `${steps.slice(0, -1).join(", ")} ${and} ${steps[steps.length - 1]}`;

/**
 * Sensitivity sliders (REQ-WEB-SLIDERS.1): matching mode, distance and re-report window switch instantly between
 * precomputed grid points, with the run without Street Light Other beneath. Each slider is a native range input
 * (keyboard operable) with the chosen value written out beside it, so color and position are never the only signal.
 */
export function Sliders() {
  const grid = useData("sensitivity_grid.json", parseSensitivityGrid);
  const excessFile = useData("excess.json", parseExcess);
  // methods.md: the excess is withheld everywhere while the headline placebo does not cover 0 (or has not loaded)
  const showExcess = excessFile.status === "ok" && excessShown(excessFile.data);
  const base = useMemo(() => defaultSetting(grid.status === "ok" ? (grid.data as { params?: { RADIUS_M?: number; WINDOW_DAYS?: number; matching?: string } }).params : null), [grid]);
  const [pick, setPick] = useState<Setting | null>(null);
  const s = pick ?? base;
  const id = useId();
  if (grid.status === "loading") return null;
  if (grid.status === "error") return <PanelError file={grid.file} error={grid.error} />;
  const point = findPoint(grid.data, s);
  const slo = grid.data.without_street_light_other;
  const isDefault = s.matching === base.matching && s.radius_m === base.radius_m && s.window_days === base.window_days;
  const na = t("sliders.no_value");
  return (
    <section className="chart-section" aria-labelledby={`${id}-h`} data-testid="sliders">
      <h2 id={`${id}-h`}>{t("sliders.heading")}</h2>
      <p>{t("sliders.intro")}</p>
      <fieldset className="slider-group">
        <legend>{t("sliders.matching")}</legend>
        {MATCHINGS.map((m: Matching) => (
          <label key={m} className="slider-radio">
            <input type="radio" name={`${id}-m`} checked={s.matching === m} onChange={() => setPick({ ...s, matching: m })} />
            <span>{t(`sliders.matching_${m}`)}</span>
          </label>
        ))}
      </fieldset>
      <div className="slider-group">
        <label htmlFor={`${id}-r`} className="slider-label">
          {t("sliders.radius")}: <output htmlFor={`${id}-r`} data-testid="radius-value">{s.radius_m}</output>
        </label>
        <input id={`${id}-r`} type="range" min={0} max={RADII.length - 1} step={1} value={stepOf(RADII, s.radius_m)} aria-valuetext={`${s.radius_m} m`} aria-describedby={radiusIsMinor(s.matching) ? `${id}-rn` : undefined} onChange={(e) => setPick({ ...s, radius_m: RADII[Number(e.target.value)] })} />
        <p className="count-note slider-stops">{t("sliders.stops", { stops: stopsText(RADII, t("sliders.stops_and")) })}</p>
        {radiusIsMinor(s.matching) ? <p className="count-note" id={`${id}-rn`}>{t("sliders.radius_note_segment")}</p> : null}
      </div>
      <div className="slider-group">
        <label htmlFor={`${id}-w`} className="slider-label">
          {t("sliders.window")}: <output htmlFor={`${id}-w`} data-testid="window-value">{s.window_days}</output>
        </label>
        <input id={`${id}-w`} type="range" min={0} max={WINDOWS.length - 1} step={1} value={stepOf(WINDOWS, s.window_days)} aria-valuetext={`${s.window_days} days`} onChange={(e) => setPick({ ...s, window_days: WINDOWS[Number(e.target.value)] })} />
        <p className="count-note slider-stops">{t("sliders.stops", { stops: stopsText(WINDOWS, t("sliders.stops_and")) })}</p>
      </div>
      <div role="group" aria-label={t("sliders.result_label")} aria-live="polite" data-testid="slider-result">
        {point ? (
          <dl className="slider-result">
            <dt>{t("sliders.headline")}</dt>
            <dd data-testid="slider-headline">{point.headline}</dd>
            <dt>{t("sliders.source_unknown")}</dt>
            <dd>{point.source_unknown}</dd>
            <dt>{t("sliders.city_rereport")}</dt>
            <dd>{point.city_rereport}</dd>
            <dt>{t("sliders.sensitivity")}</dt>
            <dd>{point.sensitivity}</dd>
            {showExcess ? (
              <>
                <dt>{t("sliders.excess_point")}</dt>
                <dd data-testid="slider-excess">{point.excess === null ? na : num1(point.excess)}</dd>
              </>
            ) : null}
            <dt>{t("sliders.stayed_fixed_point")}</dt>
            <dd>{point.stayed_fixed_rate === null ? na : pct(point.stayed_fixed_rate)}</dd>
          </dl>
        ) : (
          <p data-testid="slider-no-point">{t("sliders.no_point")}</p>
        )}
      </div>
      <p className="count-note" data-testid="slider-no-interval">{t("sliders.no_interval")}</p>
      <p className="count-note">{isDefault ? t("sliders.is_default") : t("sliders.not_default", { matching: t(`sliders.matching_${base.matching}`).toLowerCase(), radius: base.radius_m, window: base.window_days })}</p>
      <p data-testid="slider-slo">{slo ? t("sliders.without_slo", { headline: slo.headline, all: slo.all_tiers }) : t("sliders.without_slo_missing")}</p>
    </section>
  );
}
