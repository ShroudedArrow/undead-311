import { useState } from "react";
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

/**
 * Key to the map markers (REQ-WEB-MAP.1): the stencil letter for each case type, and the dashed ring for cases outside the
 * headline. It sits over the map's lower left corner, shut until asked, so the map keeps the room (reviewer-ux finding 6).
 */
export function MapLegend({ showOutline }: { showOutline: boolean }) {
    const [openChoice, setOpenChoice] = useState<boolean | null>(null);
  const open = openChoice ?? false;
  return (
    <details className="map-legend" open={open} onToggle={(e) => setOpenChoice((e.currentTarget as HTMLDetailsElement).open)} data-testid="map-legend">
      <summary>{t("map.legend_title")}</summary>
      {/* The list scrolls inside the box on short screens, so it is a focus stop with a name: keyboard users can scroll it. */}
      <ul tabIndex={0} aria-label={t("map.legend_title")}>
        {FAMILY_ORDER.map((f) => (
          <li key={f}>
            <span className="legend-mark" dangerouslySetInnerHTML={marker(f)} />
            <span>{familyLabel(f)}</span>
          </li>
        ))}
        <li>
          <span className="legend-mark" dangerouslySetInnerHTML={CLUSTER} />
          <span>{t("map.legend_cluster")}</span>
        </li>
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
