import "@fontsource/public-sans/latin-400.css";
import "@fontsource/public-sans/latin-600.css";
import "@fontsource/public-sans/latin-700.css";
import "@fontsource/courier-prime/latin-400.css";
import "@fontsource/courier-prime/latin-700.css";
import "./styles/tokens.css";
import "./styles/app.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";

/**
 * Draw the first frame once the self-hosted UI fonts are ready (at most 1.5 s), so the text does not reflow from the fallback face to
 * Public Sans a moment later and shift everything under it (layout shift, design-system.md quality floor). The fonts are same-origin files.
 */
const fontsReady = (): Promise<unknown> => {
  const fonts = typeof document !== "undefined" ? document.fonts : undefined;
  if (!fonts?.load) return Promise.resolve();
  const loads = Promise.all(["400", "600", "700"].map((w) => fonts.load(`${w} 1rem "Public Sans"`))).catch(() => undefined);
  return Promise.race([loads, new Promise((resolve) => setTimeout(resolve, 1500))]);
};

void fontsReady().then(() =>
  createRoot(document.getElementById("root") as HTMLElement).render(
    <StrictMode>
      <BrowserRouter basename={import.meta.env.BASE_URL.replace(/\/$/, "")}>
        <App />
      </BrowserRouter>
    </StrictMode>,
  ),
);
