import { useEffect, useRef, useState } from "react";
import { familyLabel } from "../lib/labels";
import { t } from "../lib/t";
import { PALETTE } from "../map/palette";
import { clusterSvg, FAMILY_ORDER, spraySvg } from "../map/sprites";

/** Markup is generated from our own seeded geometry (no user text), so it is safe to inline. */
const marker = (family: string) => ({ __html: spraySvg(0, 28, family) });
const ring = (color: string, width: number) => `<circle cx="32" cy="32" r="20.5" fill="none" stroke="${color}" stroke-width="${width}" stroke-dasharray="7 5"/>`;
const CLUSTER = { __html: clusterSvg(0, 28) };
const DASHED = {
  __html: `<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 64 64" aria-hidden="true" focusable="false">${ring(PALETTE.asphalt, 6)}${ring(PALETTE.surveyPink, 3)}</svg>`,
};

interface Props {
  /** Show the dashed-ring entry (cases outside the headline are on the map). */
  showOutline: boolean;
  /** Show the spray-dot cluster entry; false where the map never clusters (the time-lapse). */
  showCluster?: boolean;
}

/**
 * Key to the map markers (REQ-WEB-MAP.1): the stencil letter for each case type, the spray-dot cluster and the dashed ring for cases
 * outside the headline. It sits over the map's lower left corner, shut until asked, so the map keeps the room (reviewer-ux finding 6).
 * Open, it has a visible close button, and Escape closes it too; either way focus goes back to the "Marker key" button.
 */
export function MapLegend({ showOutline, showCluster = true }: Props) {
  const [open, setOpen] = useState(false);
  const details = useRef<HTMLDetailsElement>(null);
  const summary = useRef<HTMLElement>(null);
  const close = () => {
    if (details.current) details.current.open = false;
    setOpen(false);
    summary.current?.focus();
  };
  // Always listening, and reading the element's own open state: the browser's toggle event (which updates React) is asynchronous,
  // so an Escape pressed right after opening would otherwise arrive before a listener tied to `open` existed.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || !details.current?.open) return;
      close();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);
  return (
    <details ref={details} className="map-legend" open={open} onToggle={(e) => setOpen((e.currentTarget as HTMLDetailsElement).open)} data-testid="map-legend">
      <summary ref={summary}>{t("map.legend_title")}</summary>
      <button type="button" className="legend-close" aria-label={t("map.legend_close")} onClick={close}>
        <span aria-hidden="true">×</span>
      </button>
      {/* The list scrolls inside the box on short screens, so it is a focus stop with a name: keyboard users can scroll it. */}
      <ul tabIndex={0} aria-label={t("map.legend_title")}>
        {FAMILY_ORDER.map((f) => (
          <li key={f}>
            <span className="legend-mark" dangerouslySetInnerHTML={marker(f)} />
            <span>{familyLabel(f)}</span>
          </li>
        ))}
        {showCluster ? (
          <li>
            <span className="legend-mark" dangerouslySetInnerHTML={CLUSTER} />
            <span>{t("map.legend_cluster")}</span>
          </li>
        ) : null}
        {showOutline ? (
          <li>
            <span className="legend-mark" dangerouslySetInnerHTML={DASHED} />
            <span>{t("map.legend_outline")}</span>
          </li>
        ) : null}
      </ul>
    </details>
  );
}
