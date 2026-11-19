/**
 * Haunted map (REQ-WEB-MAP.1, .5). MapLibre draws the self-hosted PMTiles basemap; a deck.gl IconLayer draws the
 * possible zombies as spray-circle sprites. Loaded lazily from the page so the first view stays small (REQ-WEB-PERF.1).
 */
import type { MapboxOverlay } from "@deck.gl/mapbox";
import { ClickOnlyOverlay } from "./clickOnlyOverlay";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import { Protocol } from "pmtiles";
import { useEffect, useMemo, useRef, useState } from "react";
import type { PointRow } from "../lib/points";
import { watchOverlay } from "./overlayA11y";
import { t } from "../lib/t";
import { buildLayers, type MarkerMode } from "./layers";
import { clusterLevel, DENSITY_ZOOM, groupRows, type Cluster, type Grouped } from "./density";
import { makeAtlasCanvas } from "./sprites";
import { BOSTON_BOUNDS, BOSTON_CENTER, BOSTON_ZOOM, buildStyle, MIN_ZOOM, tilesUrl } from "./style";

let protocolAdded = false;
function ensureProtocol(): void {
  if (protocolAdded) return;
  // The worker is bundled as a same-origin asset; the default URL points at a file that is not shipped.
  maplibregl.setWorkerUrl(workerUrl);
  maplibregl.addProtocol("pmtiles", new Protocol().tile);
  protocolAdded = true;
}

/** Draw at no more than twice the CSS pixels: a phone at 2.6 pixels per CSS pixel would otherwise fill 1.7 times the pixels for no visible gain on a map. */
export const MAX_PIXEL_RATIO = 2;
const pixelRatio = (): number => Math.min(MAX_PIXEL_RATIO, typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1);

const prefersReducedMotion = (): boolean => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;

type MapHostElement = HTMLDivElement & {
  __project?: (lon: number, lat: number) => { x: number; y: number };
  __clusterPixels?: () => { x: number; y: number; count: number }[];
};

interface Props {
  rows: PointRow[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  /** IDs to ring in Cone orange (bulk-closure layer, REQ-WEB-DEATHS.1); null when the layer is off. */
  bulkIds?: ReadonlySet<string> | null;
  /** "density" clusters at city zoom (the main map); "dots" never clusters (the time-lapse). */
  mode?: MarkerMode;
  /** Zoom to this box, [west, south, east, north] ("Check my street", REQ-WEB-STREET.1). */
  bounds?: [number, number, number, number] | null;
}

export default function MapView({ rows, selectedId, onSelect, bulkIds = null, bounds = null, mode = "density" }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const overlayRef = useRef<MapboxOverlay | null>(null);
  const atlasRef = useRef<HTMLCanvasElement | null>(null);
  const onSelectRef = useRef(onSelect);
  const [failed, setFailed] = useState(false);
  const [ready, setReady] = useState(false);
  // map zoom in half steps: the density view and the marker size follow it (REQ-WEB-MAP.1)
  const [zoom, setZoom] = useState(BOSTON_ZOOM);
  onSelectRef.current = onSelect;
  const onClusterRef = useRef<(c: Cluster) => void>(() => undefined);
  // Clusters are worked out once per whole zoom level (and again when the rows or the selection change), not on every zoom step or render.
  const level = clusterLevel(zoom);
  const grouped = useMemo<Grouped>(() => (mode === "dots" ? { clusters: [], singles: rows } : groupRows(rows, level, selectedId)), [rows, level, selectedId, mode]);
  const groupedRef = useRef(grouped);
  groupedRef.current = grouped;
  onClusterRef.current = (c) => {
    const map = mapRef.current;
    if (!map) return;
    // two steps in, and always past the density threshold, so one click turns a cluster into its markers
    const to = Math.min(18, Math.max(map.getZoom() + 2, DENSITY_ZOOM + 0.2));
    map.easeTo({ center: [c.lon, c.lat], zoom: to, duration: prefersReducedMotion() ? 0 : 500 });
  };

  useEffect(() => {
    if (!host.current) return;
    let map: maplibregl.Map;
    let stopWatch: (() => void) | undefined;
    try {
      ensureProtocol();
      atlasRef.current = makeAtlasCanvas();
      map = new maplibregl.Map({
        container: host.current,
        style: buildStyle(tilesUrl(window.location.origin, import.meta.env.BASE_URL), t("map.attribution")),
        center: BOSTON_CENTER,
        zoom: BOSTON_ZOOM,
        maxBounds: BOSTON_BOUNDS,
        minZoom: MIN_ZOOM,
        maxZoom: 18,
        attributionControl: { compact: false },
        pixelRatio: pixelRatio(),
        cooperativeGestures: false,
        // control labels come from en.json (REQ-WEB-COPY.1), not the library's built-in English
        locale: {
          "NavigationControl.ZoomIn": t("map.zoom_in"),
          "NavigationControl.ZoomOut": t("map.zoom_out"),
          "AttributionControl.ToggleAttribution": t("map.attribution_toggle"),
        },
      });
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      const overlay = new ClickOnlyOverlay({ interleaved: false, layers: [], useDevicePixels: pixelRatio() });
      map.addControl(overlay as unknown as maplibregl.IControl);
      overlayRef.current = overlay;
      mapRef.current = map;
      if (host.current) stopWatch = watchOverlay(host.current);
      // Lets an end-to-end test turn a longitude and latitude into the pixel to click. It lives on the element, not on window.
      (host.current as MapHostElement).__project = (lon, lat) => {
        const p = map.project([lon, lat]);
        const r = host.current?.getBoundingClientRect();
        return { x: p.x + (r?.left ?? 0), y: p.y + (r?.top ?? 0) };
      };
      // The same for the clusters now on the map, for the end-to-end tests that click one.
      (host.current as MapHostElement).__clusterPixels = () => {
        const r = host.current?.getBoundingClientRect();
        return groupedRef.current.clusters.map((c) => {
          const p = map.project([c.lon, c.lat]);
          return { x: p.x + (r?.left ?? 0), y: p.y + (r?.top ?? 0), count: c.count };
        });
      };
      map.on("load", () => setReady(true));
      const onZoom = () => setZoom(Math.floor(map.getZoom() * 2) / 2);
      map.on("zoom", onZoom);
      map.on("zoomend", onZoom);
    } catch {
      setFailed(true);
      return;
    }
    return () => {
      stopWatch?.();
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
      layers: buildLayers({ rows, grouped, selectedId, atlas: atlasRef.current, bulkIds, onSelect: (id) => onSelectRef.current(id), compact: typeof window.matchMedia === "function" && window.matchMedia("(max-width: 640px)").matches, zoom, mode, onCluster: (c) => onClusterRef.current(c) }),
    });
  }, [rows, grouped, selectedId, ready, bulkIds, zoom, mode]);

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
      data-zoom={zoom}
      data-cluster-count={grouped.clusters.length}
      data-mode={mode}
      data-bulk-count={bulkIds ? bulkIds.size : 0}
    />
  );
}
