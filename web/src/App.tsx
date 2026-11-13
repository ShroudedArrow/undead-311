import { Route, Routes } from "react-router-dom";
import { Shell } from "./components/Shell";
import { t } from "./lib/t";
import CardRoute from "./pages/CardRoute";
import HomePage from "./pages/HomePage";

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
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
