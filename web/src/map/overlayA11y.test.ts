import { describe, expect, it } from "vitest";
import { hideOverlayFromKeyboard, watchOverlay } from "./overlayA11y";

describe("deck.gl overlay canvas (UX-56, REQ-WEB-A11Y.1)", () => {
  it("leaves the Tab order and the accessibility tree", () => {
    const c = document.createElement("canvas");
    c.tabIndex = 0;
    hideOverlayFromKeyboard(c);
    expect(c.tabIndex).toBe(-1);
    expect(c.getAttribute("aria-hidden")).toBe("true");
  });

  it("fixes a canvas added later and one whose tabindex is set again", async () => {
    const host = document.createElement("div");
    const stop = watchOverlay(host);
    const c = document.createElement("canvas");
    c.id = "deckgl-overlay";
    c.tabIndex = 0;
    host.append(c);
    await Promise.resolve();
    expect(c.tabIndex).toBe(-1);
    c.tabIndex = 0;
    await Promise.resolve();
    expect(c.tabIndex).toBe(-1);
    stop();
  });

  it("does not touch other canvases", async () => {
    const host = document.createElement("div");
    const stop = watchOverlay(host);
    const map = document.createElement("canvas");
    map.tabIndex = 0;
    host.append(map);
    await Promise.resolve();
    expect(map.tabIndex).toBe(0);
    stop();
  });
});
