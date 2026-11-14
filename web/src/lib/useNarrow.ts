import { useEffect, useState } from "react";
import { NARROW_QUERY } from "./charts";

const query = (): MediaQueryList | null => (typeof window !== "undefined" && typeof window.matchMedia === "function" ? window.matchMedia(NARROW_QUERY) : null);

/** True on screens up to 640 CSS px wide (UX-19, REQ-WEB-A11Y.1). False where matchMedia does not exist (tests). */
export function useNarrow(): boolean {
  const [narrow, setNarrow] = useState(() => query()?.matches ?? false);
  useEffect(() => {
    const mq = query();
    if (!mq) return;
    const on = () => setNarrow(mq.matches);
    on();
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return narrow;
}
