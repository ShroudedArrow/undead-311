/**
 * The deck.gl overlay canvas is a second <canvas> on top of the map. Left alone it is an unnamed Tab stop with no visible
 * focus (UX-56). The labeled Map region is the single map stop (REQ-WEB-A11Y.1), and the table view mirrors the markers
 * for keyboard users, so the overlay is taken out of the Tab order and hidden from assistive technology.
 */
export function hideOverlayFromKeyboard(canvas: HTMLElement): void {
  canvas.setAttribute("tabindex", "-1");
  canvas.setAttribute("aria-hidden", "true");
}

/** Hides every deck.gl overlay canvas under `host`, now and whenever the library sets its attributes again. Returns a stop function. */
export function watchOverlay(host: HTMLElement): () => void {
  const apply = () => host.querySelectorAll<HTMLElement>("canvas#deckgl-overlay").forEach((c) => {
    if (c.getAttribute("tabindex") !== "-1" || c.getAttribute("aria-hidden") !== "true") hideOverlayFromKeyboard(c);
  });
  apply();
  const observer = new MutationObserver(apply);
  observer.observe(host, { subtree: true, childList: true, attributes: true, attributeFilter: ["tabindex", "aria-hidden"] });
  return () => observer.disconnect();
}
