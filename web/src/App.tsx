import { Route, Routes } from "react-router-dom";
import { Shell } from "./components/Shell";
import { t } from "./lib/t";

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
        <Route index element={<h1 style={{ padding: "var(--space-3)" }}>{t("app.title")}</h1>} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
