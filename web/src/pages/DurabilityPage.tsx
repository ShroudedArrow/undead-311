import { useId, useMemo, useState } from "react";
import { FunnelChart, FunnelLegend, Leaderboard } from "../components/FunnelChart";
import { PanelError } from "../components/PanelError";
import { SurvivalChart, SurvivalTable, curveLabel } from "../components/SurvivalChart";
import { curveKind, curvesFor, type CurveKind } from "../lib/charts";
import { useData } from "../lib/data";
import { parseFunnel, parseGroups, parseSurvival, type Group } from "../lib/parse";
import { pct } from "../lib/rates";
import { t } from "../lib/t";

const KINDS: Group["kind"][] = ["department", "neighborhood", "family"];

function SurvivalPanel() {
  const survival = useData("survival.json", parseSurvival);
  const [tier, setTier] = useState<"headline" | "all">("headline");
  const [kind, setKind] = useState<Exclude<CurveKind, "all">>("family");
  const [pick, setPick] = useState("");
  const id = useId();
  const curves = survival.status === "ok" ? survival.data.curves : [];
  const citywide = curves.find((c) => c.tier_set === tier && curveKind(c.name).kind === "all") ?? null;
  const options = useMemo(() => curvesFor(curves, tier, kind), [curves, tier, kind]);
  const picked = options.find((c) => c.name === pick) ?? null;
  const shown = picked ?? citywide;
  const tableRows = [citywide, ...options].filter((c): c is NonNullable<typeof c> => c !== null);
  return (
    <section className="chart-section" aria-labelledby={`${id}-h`}>
      <h2 id={`${id}-h`}>{t("charts.survival_heading")}</h2>
      <p>{t("charts.survival_intro")}</p>
      {survival.status === "error" && <PanelError file={survival.file} error={survival.error} />}
      {survival.status === "ok" && curves.length === 0 && <p className="table-empty">{t("charts.no_curves")}</p>}
      {survival.status === "ok" && shown ? (
        <>
          <div className="chart-controls">
            <fieldset>
              <legend>{t("charts.tier_label")}</legend>
              {(["headline", "all"] as const).map((v) => (
                <label key={v}>
                  <input type="radio" name={`${id}-tier`} checked={tier === v} onChange={() => { setTier(v); setPick(""); }} />
                  <span>{t(v === "headline" ? "charts.tier_headline" : "charts.tier_all")}</span>
                </label>
              ))}
            </fieldset>
            <fieldset>
              <legend>{t("charts.kind_label")}</legend>
              {(["family", "department"] as const).map((v) => (
                <label key={v}>
                  <input type="radio" name={`${id}-kind`} checked={kind === v} onChange={() => { setKind(v); setPick(""); }} />
                  <span>{t(v === "family" ? "charts.kind_family" : "charts.kind_department")}</span>
                </label>
              ))}
            </fieldset>
            <label className="chart-pick">
              <span>{t("charts.pick_group")}</span>
              <select value={pick} onChange={(e) => setPick(e.target.value)}>
                <option value="">{t("charts.none_picked")}</option>
                {options.map((c) => (
                  <option key={c.name} value={c.name}>{curveLabel(c.name)}</option>
                ))}
              </select>
            </label>
          </div>
          <SurvivalChart curve={shown} baseline={picked ? citywide : null} tierLabel={t(tier === "headline" ? "charts.tier_headline" : "charts.tier_all")} />
          <SurvivalTable curves={tableRows} />
        </>
      ) : null}
    </section>
  );
}

function FunnelPanel() {
  const funnel = useData("funnel.json", parseFunnel);
  const groups = useData("groups.json", parseGroups);
  const [kind, setKind] = useState<Group["kind"]>("neighborhood");
  const id = useId();
  const ok = funnel.status === "ok" && groups.status === "ok";
  return (
    <section className="chart-section" aria-labelledby={`${id}-h`}>
      <h2 id={`${id}-h`}>{t("charts.funnel_heading")}</h2>
      <p>{t("charts.funnel_intro")}</p>
      {funnel.status === "error" && <PanelError file={funnel.file} error={funnel.error} />}
      {groups.status === "error" && <PanelError file={groups.file} error={groups.error} />}
      {ok ? (
        <>
          <fieldset className="chart-controls">
            <legend>{t("charts.kind_label")}</legend>
            {KINDS.map((k) => (
              <label key={k}>
                <input type="radio" name={`${id}-fk`} checked={kind === k} onChange={() => setKind(k)} />
                <span>{t(`charts.kind_${k}`)}</span>
              </label>
            ))}
          </fieldset>
          <FunnelChart groups={funnel.data.groups.filter((g) => g.kind === kind)} limits={funnel.data.limits} citywide={funnel.data.citywide} />
          <FunnelLegend />
          <p className="count-note">{t("charts.citywide_rate", { rate: pct(funnel.data.citywide) })}</p>
          <h3>{t("charts.leaderboard_heading")}</h3>
          <p>{t("charts.leaderboard_intro")}</p>
          {kind === "neighborhood" ? <p className="count-note">{t("charts.intensity_note")}</p> : null}
          <Leaderboard groups={groups.data.groups} limits={funnel.data.limits} kind={kind} />
        </>
      ) : null}
    </section>
  );
}

/** How long fixes last: survival curves, funnel plot and leaderboards (REQ-WEB-CHARTS.1-2). */
export default function DurabilityPage() {
  return (
    <div className="page">
      <h1>{t("charts.title")}</h1>
      <SurvivalPanel />
      <FunnelPanel />
    </div>
  );
}
