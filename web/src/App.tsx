import { Route, Routes } from "react-router-dom";
import { Shell } from "./components/Shell";
import { t } from "./lib/t";
import CardRoute from "./pages/CardRoute";
import CorrectionsPage from "./pages/CorrectionsPage";
import DurabilityPage from "./pages/DurabilityPage";
import HomePage from "./pages/HomePage";
import JudgePage from "./pages/JudgePage";
import MethodsPage from "./pages/MethodsPage";
import RepeatPage from "./pages/RepeatPage";
import ScorecardPage from "./pages/ScorecardPage";
import StreetPage from "./pages/StreetPage";

function NotFound() {
  return (
    <div style={{ padding: "var(--space-3)" }}>
      <p>{t("errors.not_found")}</p>
    </div>
  );
}

/** Routed app. Pages are added by later tasks of the haunted-web spec. */
export default function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route element={<HomePage />}>
          <Route index element={null} />
          <Route path="zombie/:id" element={<CardRoute />} />
        </Route>
        <Route path="scorecard" element={<ScorecardPage />} />
        <Route path="durability" element={<DurabilityPage />} />
        <Route path="repeat" element={<RepeatPage />} />
        <Route path="street" element={<StreetPage />} />
        <Route path="methods" element={<MethodsPage />} />
        <Route path="corrections" element={<CorrectionsPage />} />
        <Route path="judge" element={<JudgePage />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
