/** Remembers whether the visitor collapsed the independence bar (REQ-WEB-DESIGN.3). Storage can be missing or blocked, so every call is guarded. */
export const FOOTER_KEY = "undead311.footer-collapsed";

export function readFooterCollapsed(): boolean {
  try {
    return window.localStorage.getItem(FOOTER_KEY) === "1";
  } catch {
    return false;
  }
}

export function writeFooterCollapsed(collapsed: boolean): void {
  try {
    if (collapsed) window.localStorage.setItem(FOOTER_KEY, "1");
    else window.localStorage.removeItem(FOOTER_KEY);
  } catch {
    // storage is unavailable (private mode, blocked cookies): the choice then lasts only for this visit
  }
}
