import { useMemo, useState } from "react";
import { Link, Route, Routes, useLocation } from "react-router-dom";
import { Shell } from "./components/Shell";
import { LangContext } from "./lib/lang";
import { setLang, spanishAvailable, t, type Lang } from "./lib/t";
import CardRoute from "./pages/CardRoute";
import CorrectionsPage from "./pages/CorrectionsPage";
import DistrictPage from "./pages/DistrictPage";
import DurabilityPage from "./pages/DurabilityPage";
import HomePage from "./pages/HomePage";
import JudgePage from "./pages/JudgePage";
import MethodsPage from "./pages/MethodsPage";
import NeighborhoodRoute from "./pages/NeighborhoodRoute";
import RepeatPage from "./pages/RepeatPage";
import TimeLapsePage from "./pages/TimeLapsePage";
import ScorecardPage from "./pages/ScorecardPage";
import StreetPage from "./pages/StreetPage";

function NotFound() {
  return (
    <div className="page" data-testid="not-found">
      <h1>{t("errors.not_found_heading")}</h1>
      <p>
        {t("errors.not_found")} <Link to="/">{t("errors.not_found_link")}</Link>
      </p>
    </div>
  );
}

/** Routed app. Pages are added by later tasks of the haunted-web spec. */
export default function App() {
  const spanish = spanishAvailable({ preview: import.meta.env.VITE_SHOW_UNREVIEWED_ES === "1" });
  const { search } = useLocation();
  const [lang, setLangState] = useState<Lang>(() => (spanish && new URLSearchParams(search).get("lang") === "es" ? "es" : "en"));
  // set before the pages render, so every t() call in this pass answers in the chosen language
  setLang(spanish ? lang : "en");
  const control = useMemo(() => ({ lang, setLang: setLangState, spanish }), [lang, spanish]);
  return (
    <LangContext.Provider value={control}>
    <Routes key={lang}>
      <Route element={<Shell />}>
        <Route element={<HomePage />}>
          <Route index element={null} />
          <Route path="zombie/:id" element={<CardRoute />} />
        </Route>
        <Route path="scorecard" element={<ScorecardPage />} />
        <Route path="durability" element={<DurabilityPage />} />
        <Route path="neighborhood/:slug" element={<NeighborhoodRoute />} />
        <Route path="timelapse" element={<TimeLapsePage />} />
        <Route path="repeat" element={<RepeatPage />} />
        <Route path="districts" element={<DistrictPage />} />
        <Route path="districts/:id" element={<DistrictPage />} />
        <Route path="street" element={<StreetPage />} />
        <Route path="methods" element={<MethodsPage />} />
        <Route path="corrections" element={<CorrectionsPage />} />
        <Route path="judge" element={<JudgePage />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
    </LangContext.Provider>
  );
}
