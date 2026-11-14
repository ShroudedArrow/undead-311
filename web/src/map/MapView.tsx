/**
 * Haunted map (REQ-WEB-MAP.1, .5). MapLibre draws the self-hosted PMTiles basemap; a deck.gl IconLayer draws the
 * possible zombies as spray-circle sprites. Loaded lazily from the page so the first view stays small (REQ-WEB-PERF.1).
 */
import { IconLayer } from "@deck.gl/layers";
import { MapboxOverlay } from "@deck.gl/mapbox";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import { Protocol } from "pmtiles";
import { useEffect, useRef, useState } from "react";
import type { PointRow } from "../lib/points";
import { t } from "../lib/t";
import { iconFor, iconMapping, makeAtlasCanvas } from "./sprites";
import { BOSTON_BOUNDS, BOSTON_CENTER, BOSTON_ZOOM, buildStyle, tilesUrl } from "./style";

let protocolAdded = false;
function ensureProtocol(): void {
  if (protocolAdded) return;
  // The worker is bundled as a same-origin asset; the default URL points at a file that is not shipped.
  maplibregl.setWorkerUrl(workerUrl);
  maplibregl.addProtocol("pmtiles", new Protocol().tile);
  protocolAdded = true;
}

const prefersReducedMotion = (): boolean => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;

interface Props {
  rows: PointRow[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export default function MapView({ rows, selectedId, onSelect }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const overlayRef = useRef<MapboxOverlay | null>(null);
  const atlasRef = useRef<HTMLCanvasElement | null>(null);
  const onSelectRef = useRef(onSelect);
  const [failed, setFailed] = useState(false);
  const [ready, setReady] = useState(false);
  onSelectRef.current = onSelect;

  useEffect(() => {
    if (!host.current) return;
    let map: maplibregl.Map;
    try {
      ensureProtocol();
      atlasRef.current = makeAtlasCanvas();
      map = new maplibregl.Map({
        container: host.current,
        style: buildStyle(tilesUrl(window.location.origin, import.meta.env.BASE_URL), t("map.attribution")),
        center: BOSTON_CENTER,
        zoom: BOSTON_ZOOM,
        maxBounds: BOSTON_BOUNDS,
        minZoom: 9,
        maxZoom: 18,
        attributionControl: { compact: false },
        cooperativeGestures: false,
        // control labels come from en.json (REQ-WEB-COPY.1), not the library's built-in English
        locale: {
          "NavigationControl.ZoomIn": t("map.zoom_in"),
          "NavigationControl.ZoomOut": t("map.zoom_out"),
          "AttributionControl.ToggleAttribution": t("map.attribution_toggle"),
        },
      });
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      const overlay = new MapboxOverlay({ interleaved: false, layers: [] });
      map.addControl(overlay as unknown as maplibregl.IControl);
      overlayRef.current = overlay;
      mapRef.current = map;
      map.on("load", () => setReady(true));
    } catch {
      setFailed(true);
      return;
    }
    return () => {
      overlayRef.current = null;
      mapRef.current = null;
      setReady(false);
      map.remove();
    };
  }, []);

  useEffect(() => {
    const overlay = overlayRef.current;
    if (!overlay || !atlasRef.current) return;
    overlay.setProps({
      layers: [
        new IconLayer<PointRow>({
          id: "zombies",
          data: rows,
          pickable: true,
          // never let loaders.gl fetch worker scripts from a CDN (REQ-WEB-PERF.2)
          loadOptions: { worker: false },
          iconAtlas: atlasRef.current as unknown as string,
          iconMapping: iconMapping(),
          getIcon: (d) => iconFor(d.id, d.tier),
          getPosition: (d) => [d.lon, d.lat],
          getSize: (d) => (d.id === selectedId ? 44 : 30),
          sizeUnits: "pixels",
          sizeMinPixels: 14,
          updateTriggers: { getSize: [selectedId] },
          onClick: (info) => {
            if (info.object) onSelectRef.current(info.object.id);
          },
        }),
      ],
    });
  }, [rows, selectedId, ready]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !selectedId) return;
    const row = rows.find((r) => r.id === selectedId);
    if (row) map.easeTo({ center: [row.lon, row.lat], zoom: Math.max(map.getZoom(), 14), duration: prefersReducedMotion() ? 0 : 600 });
    // Only re-center when the selection changes, not when filters change the rows.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  if (failed) return <p className="panel-error" role="status">{t("map.unsupported")}</p>;
  return (
    <div
      ref={host}
      className="map-host"
      role="region"
      aria-label={t("map.region_label")}
      data-testid="map"
      data-ready={ready ? "true" : "false"}
      data-marker-count={rows.length}
    />
  );
}
