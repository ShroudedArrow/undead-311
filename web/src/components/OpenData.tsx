import { useState } from "react";
import { Link } from "react-router-dom";
import { allShardKeys, useZombieIndex, useZombieShards } from "../lib/shards";
import { zombiesToCsv } from "../lib/openData";
import { t } from "../lib/t";

/** Dataset download with its license, on the methods page (REQ-WEB-OPEN.1), and the before/after note (REQ-WEB-OPEN.3). */
export function OpenData() {
  const [want, setWant] = useState(false);
  const index = useZombieIndex(want);
  const zombies = useZombieShards(want && index.status === "ok" ? allShardKeys(index.data.shards) : null);
  const base = import.meta.env.BASE_URL;
  const download = () => {
    if (zombies.status !== "ok") return;
    const url = URL.createObjectURL(new Blob([zombiesToCsv(zombies.data.zombies)], { type: "text/csv;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "undead311-possible-zombies.csv";
    a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <section className="chart-section" aria-labelledby="open-h" data-testid="open-data">
      <h2 id="open-h">{t("open.heading")}</h2>
      <p>{t("open.intro")}</p>
      <p className="open-links">
        <a href={`${base}data/zombies/index.json`} download>{t("open.json")}</a>
        {!want ? <button type="button" onClick={() => setWant(true)}>{t("open.csv")}</button> : zombies.status === "ok" ? (
          <button type="button" onClick={download}>{t("open.csv")}</button>
        ) : null}
      </p>
      <p role="status">
        {want && zombies.status === "loading" ? t("open.csv_preparing") : null}
        {want && (zombies.status === "error" || index.status === "error") ? t("open.csv_error") : null}
        {want && zombies.status === "ok" ? t("open.csv_rows", { count: zombies.data.zombies.length }) : null}
      </p>
      <p><Link to="/districts">{t("nav.districts")}</Link></p>
      <p data-testid="open-license-dataset">
        {t("open.license_dataset")} <a href="https://opendatacommons.org/licenses/pddl/1-0/" rel="noopener noreferrer">{t("open.license_text")}</a>
      </p>
      <p>{t("open.license_cases")}</p>
      <p className="count-note">{t("open.floor")}</p>
      <p data-testid="before-after-note" className="count-note">{t("open.before_after_missing")}</p>
    </section>
  );
}
