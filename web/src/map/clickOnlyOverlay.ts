import { MapboxOverlay } from "@deck.gl/mapbox";

type MapMouseEvent = { type: string; point?: { x: number; y: number } };
type DeckLike = { isInitialized?: boolean; _onPointerDown: (e: unknown) => void };

/**
 * The deck.gl overlay, picking only on a click or tap (REQ-WEB-PERF).
 *
 * deck.gl picks under the pointer on every frame the mouse moves (for a hover cursor and onHover, which this map does not use) and
 * again on every press, including the press that starts a pan. A pick draws the pickable layers into an off-screen buffer and reads
 * it back, which makes the main thread wait for the GPU to finish everything queued. In the profile each such wait during a zoom
 * or pan was a long task (up to 3.5 s on software GL). Here hover picking is dropped and the press pick is moved to the click: a
 * pan never picks, and a click or tap picks once at the point it landed, so a marker or cluster opens as before.
 */
export class ClickOnlyOverlay extends MapboxOverlay {
  constructor(props: ConstructorParameters<typeof MapboxOverlay>[0]) {
    super(props);
    const self = this as unknown as { _handleMouseEvent: (e: MapMouseEvent) => void; _deck?: DeckLike };
    const forward = self._handleMouseEvent;
    self._handleMouseEvent = (event) => {
      if (event.type === "mousemove" || event.type === "mouseout") return;
      const deck = self._deck;
      if (!deck || !deck.isInitialized) return;
      if (event.type === "mousedown") {
        // keep the overlay's own bookkeeping (the press point that drag events are measured from), without the pick
        const pick = deck._onPointerDown;
        deck._onPointerDown = () => undefined;
        try {
          forward(event);
        } finally {
          deck._onPointerDown = pick;
        }
        return;
      }
      if ((event.type === "click" || event.type === "dblclick") && event.point) deck._onPointerDown({ type: "pointerdown", offsetCenter: event.point, srcEvent: event });
      forward(event);
    };
  }
}
