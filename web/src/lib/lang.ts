import { createContext, useContext } from "react";
import type { Lang } from "./t";

export interface LangControl {
  lang: Lang;
  setLang: (l: Lang) => void;
  /** True when Spanish may be shown (reviewed, or not a production build; REQ-WEB-ES.1). */
  spanish: boolean;
}
export const LangContext = createContext<LangControl>({ lang: "en", setLang: () => undefined, spanish: false });
export const useLang = (): LangControl => useContext(LangContext);
