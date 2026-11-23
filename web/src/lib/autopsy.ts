/** Small pure helpers for the autopsy card (REQ-WEB-CARD.1-3). */
import { haversineM } from "./geo";
import { t } from "./t";

/**
 * The Skeptic's note as separate objections. The pipeline stores one string; its sentences are the objections. A sentence ends at
 * ". ", "? " or "! " followed by a capital letter or an opening bracket, so "Foster St & Washington St:" and "23 m from" stay whole.
 */
export function splitObjections(notes: string | null | undefined): string[] {
  const text = (notes ?? "").replace(/\s+/g, " ").trim();
  if (!text) return [];
  return text
    .split(/(?<=[.!?])\s+(?=[A-Z(])/)
    .map((s) => s.trim())
    .filter(Boolean);
}

/** Meters between the original case and the re-report, or null when either has no point. */
export function distanceApartM(a: { lat: number; lon: number }, b: { lat: number; lon: number }): number | null {
  const ok = [a.lat, a.lon, b.lat, b.lon].every((v) => typeof v === "number" && Number.isFinite(v));
  return ok ? haversineM(a.lat, a.lon, b.lat, b.lon) : null;
}

/** "34 m" under a kilometer, "1.2 km" above; a point closer than half a meter reads "0 m". */
export function formatDistance(meters: number): string {
  if (meters >= 1000) return t("card.km", { km: (Math.round(meters / 100) / 10).toString() });
  return t("card.meters", { meters: Math.round(meters) });
}
