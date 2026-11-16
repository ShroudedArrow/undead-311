import { bandPath, dayTicks, tickPct, yTitle, yTitleAttrs, chartDims, curveKind, linePath, linear, niceTicks } from "../lib/charts";
import { groupLabel } from "../lib/labels";
import type { Curve } from "../lib/parse";
import { pct } from "../lib/rates";
import { t } from "../lib/t";
import { useNarrow } from "../lib/useNarrow";

/** Display name for a curve: "Citywide", a case type or a department. */
export function curveLabel(name: string): string {
  const { kind, key } = curveKind(name);
  return kind === "all" ? t("charts.citywide") : groupLabel(kind === "family" ? "family" : "department", key);
}

function share(c: Curve, at: "at_7" | "at_30" | "at_90"): string {
  const i = at === "at_7" ? 7 : at === "at_30" ? 30 : 90;
  const v = c[at];
  if (v === null) return "";
  const lo = c.lo[c.times.indexOf(i)];
  const hi = c.hi[c.times.indexOf(i)];
  return lo === undefined || hi === undefined ? pct(v) : t("charts.share_with_interval", { share: pct(v), lo: pct(lo), hi: pct(hi) });
}

/**
 * One survival curve with its 95% band, optionally over a dashed citywide curve (REQ-WEB-CHARTS.1). The band is always
 * drawn. Two curves differ by line style (solid and dashed), not only by place, and a table below repeats every number.
 */
export function SurvivalChart({ curve, baseline, tierLabel }: { curve: Curve; baseline: Curve | null; tierLabel: string }) {
  const { W, H, M, narrow } = chartDims(useNarrow(), 320);
  const lastDay = Math.max(...curve.times, 1);
  const x = linear(0, lastDay, M.l, W - M.r);
  // the vertical range starts below the lowest interval bound (rounded down to 5%), so the band is readable when most fixes hold
  const floor = Math.max(0, Math.min(0.95, Math.floor(Math.min(...curve.lo, ...(baseline?.lo ?? [1])) * 20) / 20));
  const y = linear(floor, 1, H - M.b, M.t);
  const xs = curve.times.map(x);
  const ticksX = dayTicks(lastDay, (W - M.r - M.l) / lastDay);
  const ticksY = niceTicks(floor, 1, narrow ? 4 : 5);
  const unknown = t("charts.share_unknown");
  const label = t("charts.survival_label", {
    name: curveLabel(curve.name), tier: tierLabel, at7: pct(curve.at_7) || unknown, at30: pct(curve.at_30) || unknown, at90: pct(curve.at_90) || unknown,
  }) + (baseline ? " " + t("charts.survival_label_base", { name: curveLabel(baseline.name), at7: pct(baseline.at_7) || unknown, at30: pct(baseline.at_30) || unknown, at90: pct(baseline.at_90) || unknown }) : "");
  return (
    <svg className={narrow ? "chart chart-narrow" : "chart"} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label} data-testid="survival-chart" focusable="false">
      {ticksY.map((v) => (
        <g key={v}>
          <line className="chart-grid" x1={M.l} x2={W - M.r} y1={y(v)} y2={y(v)} />
          <text className="chart-tick" x={M.l - 6} y={y(v) + 4} textAnchor="end">{tickPct(v)}</text>
        </g>
      ))}
      {ticksX.map((d) => (
        <g key={d}>
          <line className="chart-grid" x1={x(d)} x2={x(d)} y1={M.t} y2={H - M.b} />
          <text className="chart-tick" x={x(d)} y={H - M.b + 16} textAnchor="middle">{d}</text>
        </g>
      ))}
      <text className="chart-axis" x={(M.l + W - M.r) / 2} y={H - 6} textAnchor="middle">{t("charts.axis_days")}</text>
      <text className="chart-axis" data-testid="y-title" {...yTitleAttrs(yTitle({ W, H, M, narrow }))}>{t("charts.axis_share")}</text>
      <path className="chart-band" data-testid="survival-band" d={bandPath(xs, curve.lo.map(y), curve.hi.map(y))} />
      {baseline ? <path className="chart-line chart-line-base" d={linePath(baseline.times.map(x), baseline.survival.map(y))} /> : null}
      <path className="chart-line" d={linePath(xs, curve.survival.map(y))} />
    </svg>
  );
}

/** Key for the survival chart: the picked group (solid), the citywide curve (dashed, only when a group is picked) and the band (UX-22). */
export function SurvivalLegend({ curve, baseline }: { curve: Curve; baseline: Curve | null }) {
  return (
    <ul className="chart-legend" data-testid="survival-legend">
      <li><svg width="28" height="10" aria-hidden="true" focusable="false"><line className="chart-line" x1="0" x2="28" y1="5" y2="5" /></svg> {curveLabel(curve.name)}</li>
      {baseline ? <li><svg width="28" height="10" aria-hidden="true" focusable="false"><line className="chart-line chart-line-base" x1="0" x2="28" y1="5" y2="5" /></svg> {t("charts.citywide")}</li> : null}
      <li><svg width="28" height="14" aria-hidden="true" focusable="false"><rect className="chart-band" x="0" y="1" width="28" height="12" /></svg> {t("charts.legend_band")}</li>
    </ul>
  );
}

/** Table that mirrors the chart: shares at 7, 30 and 90 days with intervals, and the half-life (REQ-WEB-CHARTS.1, REQ-WEB-A11Y.1). */
export function SurvivalTable({ curves }: { curves: readonly Curve[] }) {
  return (
    <div className="table-wrap chart-table" tabIndex={0} role="region" aria-label={t("charts.survival_table_caption")}>
      <table className="zombie-table" data-testid="survival-table">
        <caption>{t("charts.survival_table_caption")}</caption>
        <thead>
          <tr>
            <th scope="col">{t("charts.col_group")}</th>
            <th scope="col">{t("charts.col_7")}</th>
            <th scope="col">{t("charts.col_30")}</th>
            <th scope="col">{t("charts.col_90")}</th>
            <th scope="col">{t("charts.col_half")}</th>
          </tr>
        </thead>
        <tbody>
          {curves.map((c) => (
            <tr key={`${c.name}|${c.tier_set}`}>
              <th scope="row">{curveLabel(c.name)}</th>
              <td>{share(c, "at_7")}</td>
              <td>{share(c, "at_30")}</td>
              <td>{share(c, "at_90")}</td>
              <td>{c.half_life === null ? t("charts.half_life_none") : t("charts.half_life_days", { days: c.half_life })}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
