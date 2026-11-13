import { t } from "./lib/t";

/** Scaffold only: the haunted-web spec replaces this with the routed app. */
export default function App() {
  return (
    <main>
      <h1>{t("app.title")}</h1>
      <footer>{t("app.footer_independent")}</footer>
    </main>
  );
}
