import { yTitleAttrs, yTitle, tickPct, chartDims, intensityText, leaderboard, linePath, linear, logScale, niceTicks, unusualDirection } from "../lib/charts";
import { groupLabel } from "../lib/labels";
import type { FunnelLimit, Group } from "../lib/parse";
import { pct } from "../lib/rates";
import { t } from "../lib/t";
import { useNarrow } from "../lib/useNarrow";

/**
 * Funnel plot: each group's raw rate against its n, with 95% and 99.8% limits around the citywide rate (REQ-WEB-CHARTS.2).
 * Groups outside the 99.8% limits are marked by direction: a pink diamond above the upper limit (more resurrections than chance
 * explains), an Asphalt square below the lower limit (fewer). All others are circles, so shape and the table carry the signal.
 * Pink never marks a group with fewer resurrections than chance (UX-17).
 */
export function FunnelChart({ groups, limits, citywide }: { groups: readonly Group[]; limits: readonly FunnelLimit[]; citywide: number | null }) {
  const { W, H, M, narrow } = chartDims(useNarrow(), 360);
  const sorted = [...limits].sort((a, b) => a.n - b.n);
  const maxN = Math.max(...sorted.map((l) => l.n), ...groups.map((g) => g.n), 2);
  // the vertical range fits the groups, not the very wide limits of the smallest n; those lines are clipped at the top
  const maxY = Math.min(1, Math.max(0.05, ...groups.map((g) => g.raw ?? 0), citywide ?? 0) * 1.25);
  const yTicks = niceTicks(0, maxY, narrow ? 4 : 5);
  const yTop = Math.max(maxY, yTicks[yTicks.length - 1]);
  const x = logScale(1, maxN, M.l, W - M.r);
  const y = linear(0, yTop, H - M.b, M.t);
  const xs = sorted.map((l) => x(l.n));
  const dirs = groups.map((g) => unusualDirection(g, limits));
  const aboveCount = dirs.filter((d) => d === "above").length;
  const belowCount = dirs.filter((d) => d === "below").length;
  const xTicks = [1, 10, 100, 1000, 10000].filter((n) => n <= maxN);
  return (
    <svg className={narrow ? "chart chart-narrow" : "chart"} viewBox={`0 0 ${W} ${H}`} role="img" focusable="false" data-testid="funnel-chart"
      aria-label={t("charts.funnel_label", { count: groups.length, rate: pct(citywide), above: aboveCount, below: belowCount })}>
      {yTicks.map((v) => (
        <g key={v}>
          <line className="chart-grid" x1={M.l} x2={W - M.r} y1={y(v)} y2={y(v)} />
          <text className="chart-tick" x={M.l - 6} y={y(v) + 4} textAnchor="end">{tickPct(v)}</text>
        </g>
      ))}
      {xTicks.map((n) => (
        <g key={n}>
          <line className="chart-grid" x1={x(n)} x2={x(n)} y1={M.t} y2={H - M.b} />
          <text className="chart-tick" x={x(n)} y={H - M.b + 16} textAnchor="middle">{n}</text>
        </g>
      ))}
      <text className="chart-axis" x={(M.l + W - M.r) / 2} y={H - 6} textAnchor="middle">{t("charts.funnel_axis_n")}</text>
      <text className="chart-axis" data-testid="y-title" {...yTitleAttrs(yTitle({ W, H, M, narrow }))}>{t("charts.funnel_axis_rate")}</text>
      <defs>
        <clipPath id="funnel-clip">
          <rect x={M.l} y={M.t} width={W - M.l - M.r} height={H - M.t - M.b} />
        </clipPath>
      </defs>
      {sorted.length > 1 ? (
        <g clipPath="url(#funnel-clip)">
          <path className="chart-line chart-line-limit95" d={linePath(xs, sorted.map((l) => y(l.hi95)))} />
          <path className="chart-line chart-line-limit95" d={linePath(xs, sorted.map((l) => y(l.lo95)))} />
          <path className="chart-line chart-line-limit998" d={linePath(xs, sorted.map((l) => y(l.hi998)))} />
          <path className="chart-line chart-line-limit998" d={linePath(xs, sorted.map((l) => y(l.lo998)))} />
        </g>
      ) : null}
      {citywide !== null ? <line className="chart-line chart-line-base" x1={M.l} x2={W - M.r} y1={y(citywide)} y2={y(citywide)} /> : null}
      {groups.filter((g) => g.raw !== null && g.n > 0).map((g) => {
        const cx = x(g.n);
        const cy = y(g.raw as number);
        const dir = unusualDirection(g, limits);
        const name = t("charts.mark_title", { name: groupLabel(g.kind, g.name), rate: pct(g.raw), n: g.n, side: dir === null ? "" : t(`charts.side_${dir}`) }).trim();
        if (dir === "above") {
          return (
            <polygon key={`${g.kind}|${g.name}`} className="funnel-mark funnel-above" points={`${cx},${cy - 8} ${cx + 8},${cy} ${cx},${cy + 8} ${cx - 8},${cy}`}>
              <title>{name}</title>
            </polygon>
          );
        }
        return dir === "below" ? (
          <rect key={`${g.kind}|${g.name}`} className="funnel-mark funnel-below" x={cx - 6} y={cy - 6} width={12} height={12}>
            <title>{name}</title>
          </rect>
        ) : (
          <circle key={`${g.kind}|${g.name}`} className="funnel-mark funnel-typical" cx={cx} cy={cy} r={5}>
            <title>{name}</title>
          </circle>
        );
      })}
    </svg>
  );
}

export function FunnelLegend() {
  return (
    <ul className="chart-legend">
      <li><svg width="28" height="10" aria-hidden="true" focusable="false"><line className="chart-line chart-line-limit95" x1="0" x2="28" y1="5" y2="5" /></svg> {t("charts.limit_95")}</li>
      <li><svg width="28" height="10" aria-hidden="true" focusable="false"><line className="chart-line chart-line-limit998" x1="0" x2="28" y1="5" y2="5" /></svg> {t("charts.limit_998")}</li>
      <li><svg width="14" height="14" aria-hidden="true" focusable="false"><circle className="funnel-mark funnel-typical" cx="7" cy="7" r="5" /></svg> {t("charts.mark_typical")}</li>
      <li><svg width="18" height="18" aria-hidden="true" focusable="false"><polygon className="funnel-mark funnel-above" points="9,1 17,9 9,17 1,9" /></svg> {t("charts.mark_above")}</li>
      <li><svg width="16" height="16" aria-hidden="true" focusable="false"><rect className="funnel-mark funnel-below" x="2" y="2" width="12" height="12" /></svg> {t("charts.mark_below")}</li>
    </ul>
  );
}

/** Leaderboard of shrunk rates with intervals, n and reporting intensity beside every row (REQ-WEB-CHARTS.2). */
export function Leaderboard({ groups, limits, kind }: { groups: readonly Group[]; limits: readonly FunnelLimit[]; kind: Group["kind"] }) {
  const rows = leaderboard(groups, kind, limits);
  if (rows.length === 0) return <p className="table-empty">{t("charts.no_groups")}</p>;
  return (
    <div className="table-wrap chart-table" tabIndex={0} role="region" aria-label={t("charts.leaderboard_caption")}>
      <table className="zombie-table" data-testid="leaderboard">
        <caption>{t("charts.leaderboard_caption")}</caption>
        <thead>
          <tr>
            <th scope="col">{t("charts.col_name")}</th>
            <th scope="col">{t("charts.col_shrunk")}</th>
            <th scope="col">{t("charts.col_interval")}</th>
            <th scope="col">{t("charts.col_raw")}</th>
            <th scope="col">{t("charts.col_n")}</th>
            <th scope="col">{t("charts.col_intensity")}</th>
            <th scope="col">{t("charts.col_flag")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((g) => {
            const intensity = intensityText(g);
            return (
              <tr key={g.name} data-unusual={g.unusualShown ? "true" : "false"} data-direction={g.direction ?? ""}>
                <th scope="row">{groupLabel(kind === "family" ? "family" : kind, g.name)}</th>
                <td>{pct(g.shrunk)}</td>
                <td>{g.lo === null || g.hi === null ? "" : t("charts.interval_text", { lo: pct(g.lo), hi: pct(g.hi) })}</td>
                <td>{pct(g.raw)}</td>
                <td>{g.n}</td>
                <td>{intensity === null ? t("charts.intensity_missing") : t("charts.intensity_value", { value: intensity })}</td>
                <td>{g.direction === null ? t("charts.typical") : t(`charts.unusual_${g.direction}`)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
