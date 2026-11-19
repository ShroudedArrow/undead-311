import { describe, expect, it, vi } from "vitest";
import { ClickOnlyOverlay } from "./clickOnlyOverlay";

describe("ClickOnlyOverlay (REQ-WEB-PERF)", () => {
  const make = () => {
    const overlay = new ClickOnlyOverlay({ interleaved: false, layers: [] });
    const calls: string[] = [];
    const deck = {
      isInitialized: true,
      _onPointerMove: vi.fn(() => calls.push("move")),
      _onPointerDown: vi.fn((e: { offsetCenter: { x: number; y: number } }) => calls.push(`down@${e.offsetCenter.x},${e.offsetCenter.y}`)),
      _onEvent: vi.fn((e: { type: string }) => calls.push(e.type)),
    };
    (overlay as unknown as { _deck: unknown })._deck = deck;
    const handle = (overlay as unknown as { _handleMouseEvent: (e: unknown) => void })._handleMouseEvent;
    const at = (type: string, x = 5, y = 6) => handle({ type, point: { x, y }, originalEvent: { clientX: x, clientY: y } });
    return { deck, at, calls };
  };
  it("does not pick on mouse move or mouse out, which waited for the GPU on every frame", () => {
    const { deck, at } = make();
    at("mousemove");
    at("mouseout");
    expect(deck._onPointerMove).not.toHaveBeenCalled();
  });
  it("does not pick on the press that starts a pan", () => {
    const { deck, at } = make();
    at("mousedown");
    expect(deck._onPointerDown).not.toHaveBeenCalled();
  });
  it("picks once on a click, at the click point, before deck.gl handles the click, so a marker or cluster opens as before", () => {
    const { at, calls } = make();
    at("mousedown", 10, 12);
    at("click", 10, 12);
    expect(calls).toEqual(["down@10,12", "click"]);
  });
});
