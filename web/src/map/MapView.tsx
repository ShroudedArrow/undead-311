/**
 * Haunted map (REQ-WEB-MAP.1, .5). MapLibre draws the self-hosted PMTiles basemap; a deck.gl IconLayer draws the
 * possible zombies as spray-circle sprites. Loaded lazily from the page so the first view stays small (REQ-WEB-PERF.1).
 */
import { MapboxOverlay } from "@deck.gl/mapbox";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import { Protocol } from "pmtiles";
import { useEffect, useRef, useState } from "react";
import type { PointRow } from "../lib/points";
import { t } from "../lib/t";
import { buildLayers } from "./layers";
import { makeAtlasCanvas } from "./sprites";
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
  /** IDs to ring in Cone orange (bulk-closure layer, REQ-WEB-DEATHS.1); null when the layer is off. */
  bulkIds?: ReadonlySet<string> | null;
  /** Zoom to this box, [west, south, east, north] ("Check my street", REQ-WEB-STREET.1). */
  bounds?: [number, number, number, number] | null;
}

export default function MapView({ rows, selectedId, onSelect, bulkIds = null, bounds = null }: Props) {
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
      layers: buildLayers({ rows, selectedId, atlas: atlasRef.current, bulkIds, onSelect: (id) => onSelectRef.current(id) }),
    });
  }, [rows, selectedId, ready, bulkIds]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !selectedId) return;
    const row = rows.find((r) => r.id === selectedId);
    if (row) map.easeTo({ center: [row.lon, row.lat], zoom: Math.max(map.getZoom(), 14), duration: prefersReducedMotion() ? 0 : 600 });
    // Only re-center when the selection changes, not when filters change the rows.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  const boundsKey = bounds ? bounds.join(",") : "";
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !bounds) return;
    const [w, so, e, n] = bounds;
    map.fitBounds([[w, so], [e, n]], { padding: 48, maxZoom: 17, duration: prefersReducedMotion() ? 0 : 600 });
    // Only when the box changes; the array identity changes on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [boundsKey, ready]);

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
      data-bulk-count={bulkIds ? bulkIds.size : 0}
    />
  );
}
