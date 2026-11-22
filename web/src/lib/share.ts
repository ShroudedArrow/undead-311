/**
 * Share images and permalinks (REQ-WEB-LINKS.1-2). Plain TypeScript with no Vite imports, so the build script
 * (scripts/make-share-images.ts) and the browser use the same file names and the same template.
 * Share images are static files rendered at build time from a template; there is no runtime service.
 */

import { spraySvg } from "../map/sprites.ts";

export const SHARE_W = 1200;
export const SHARE_H = 630;

const PALETTE = { concrete: "#CDCBC6", asphalt: "#2E3134", white: "#F4F4EF", pink: "#FF3EA5", canary: "#EFE08A" } as const;

/** A file-name-safe slug: lower case letters and digits, single dashes. "101001:101002" gives "101001-101002". */
export function shareSlug(s: string | null | undefined): string {
  return (s || "unknown").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "unknown";
}

/** Path of a zombie's share image under the site root (no leading slash). */
export const zombieImagePath = (zombieId: string): string => `share/zombie/${shareSlug(zombieId)}.png`;
/** Path of a neighborhood's share image under the site root. */
export const neighborhoodImagePath = (name: string | null | undefined): string => `share/neighborhood/${shareSlug(name)}.png`;
/** Path of a council district's share image under the site root. */
export const districtImagePath = (district: string): string => `share/district/${shareSlug(district)}.png`;
/** Path of the home page's image, which is also the generic site image every other page falls back to. */
export const SITE_IMAGE_PATH = "share/site.png";

export const esc = (s: string): string => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
export const fill = (template: string, params: Record<string, string | number>): string => template.replace(/\{(\w+)\}/g, (m, k: string) => (k in params ? String(params[k]) : m));

export interface ShareText {
  /** The form header line on a zombie image; optional so older callers still work. */
  report_title?: string;
  district_kicker: string;
  district_line: string;
  home_kicker: string;
  home_line: string;
  zombie_kicker: string;
  zombie_line: string;
  zombie_where: string;
  neighborhood_kicker: string;
  neighborhood_line: string;
  neighborhood_top: string;
  footer: string;
  stamp_closed: string;
  stamp_again: string;
}

/** The strings of en.json `card` that `formatGap` uses, so the build script words a gap exactly as the card does. */
export interface GapText {
  day: string;
  days: string;
  hour: string;
  hours: string;
  minute: string;
  minutes: string;
  under_minute: string;
}

/** Same words as `formatGap` in format.ts (a test compares them), without importing the Vite-only copy loader. */
export function gapWords(days: number, g: GapText): string {
  const d = Math.max(0, days);
  const rounded = Math.round(d * 10) / 10;
  if (rounded >= 1) return rounded === 1 ? g.day : fill(g.days, { days: rounded });
  const hours = Math.round(d * 24);
  if (hours >= 1) return hours === 1 ? g.hour : fill(g.hours, { n: hours });
  const minutes = Math.round(d * 1440);
  if (minutes >= 1) return minutes === 1 ? g.minute : fill(g.minutes, { n: minutes });
  return g.under_minute;
}

export interface ZombieShare {
  familyLabel: string;
  neighborhood: string;
  gap: string;
}
export interface NeighborhoodShare {
  neighborhood: string;
  count: number;
  topFamilyLabel: string | null;
  topFamilyCount: number;
}

/** The map's spray-circle marker, inlined as an image so the share card carries the signature mark (UX-44). */
const sprayImg = (): string => `<img class="circle" alt="" src="data:image/svg+xml;base64,${btoa(spraySvg(0, 64))}">`;

const css = (fonts: string): string => `
${fonts}
*{box-sizing:border-box}
html,body{margin:0;width:${SHARE_W}px;height:${SHARE_H}px}
body{background:${PALETTE.concrete};color:${PALETTE.asphalt};font-family:"Public Sans",system-ui,sans-serif;display:flex;flex-direction:column;justify-content:space-between;padding:56px 64px;position:relative;overflow:hidden}
.kicker{font-size:32px;font-weight:700;margin:0}
.circle{display:inline-block;width:64px;height:64px;vertical-align:-14px;margin-right:14px}
h1{font-size:76px;line-height:1.05;margin:20px 0 0;max-width:1000px}
.line{font-size:36px;line-height:1.3;margin:24px 0 0;max-width:1000px}
.stamps{display:flex;gap:24px;margin:0}
.stamp{font-family:"Courier Prime",monospace;font-weight:700;font-size:34px;border:5px solid ${PALETTE.asphalt};padding:6px 18px;background:${PALETTE.white}}
.stamp.closed{text-decoration:line-through}
.foot{font-size:24px;margin:0}
.formline{font-family:"Courier Prime",monospace;font-weight:700;font-size:26px;margin:0 0 22px;padding-bottom:10px;border-bottom:5px solid ${PALETTE.asphalt};max-width:1000px}
.copies{position:absolute;top:0;right:0;bottom:0;width:48px;background:${PALETTE.canary};border-left:5px solid ${PALETTE.asphalt}}`;

const page = (fonts: string, body: string): string => `<!doctype html><html lang="en"><head><meta charset="utf-8"><style>${css(fonts)}</style></head><body><div class="copies" aria-hidden="true"></div>${body}</body></html>`;

/** The 1200 by 630 page for one possible zombie. `fonts` is the @font-face CSS (file URLs when rendered at build time). */
export function zombieShareHtml(d: ZombieShare, text: ShareText, fonts = ""): string {
  const where = fill(text.zombie_where, { family: d.familyLabel, neighborhood: d.neighborhood });
  return page(
    fonts,
    `<div>${text.report_title ? `<p class="formline">${esc(text.report_title)}</p>` : ""}<p class="kicker">${sprayImg()}${esc(text.zombie_kicker)}</p><h1>${esc(where)}</h1><p class="line">${esc(fill(text.zombie_line, { gap: d.gap }))}</p></div>` +
      `<p class="stamps"><span class="stamp closed">${esc(text.stamp_closed)}</span><span class="stamp">${esc(text.stamp_again)}</span></p><p class="foot">${esc(text.footer)}</p>`,
  );
}

/** The page for one neighborhood: the headline count and the most common case type. */
export function neighborhoodShareHtml(d: NeighborhoodShare, text: ShareText, fonts = ""): string {
  const top = d.topFamilyLabel ? `<p class="line">${esc(fill(text.neighborhood_top, { family: d.topFamilyLabel, count: d.topFamilyCount }))}</p>` : "";
  return page(
    fonts,
    `<div><p class="kicker">${sprayImg()}${esc(text.neighborhood_kicker)}</p><h1>${esc(d.neighborhood)}</h1><p class="line">${esc(fill(text.neighborhood_line, { count: d.count }))}</p>${top}</div>` +
      `<p class="foot">${esc(text.footer)}</p>`,
  );
}

export interface DistrictShare {
  district: string;
  count: number;
}

/** The page for one council district: the headline count. */
export function districtShareHtml(d: DistrictShare, text: ShareText, fonts = ""): string {
  return page(
    fonts,
    `<div><p class="kicker">${sprayImg()}${esc(text.district_kicker)}</p><h1>${esc(d.district)}</h1><p class="line">${esc(fill(text.district_line, { count: d.count }))}</p></div>` +
      `<p class="foot">${esc(text.footer)}</p>`,
  );
}

/** The home page's image, also the generic site image: the app's own line and the citywide headline count. */
export function siteShareHtml(d: { heroLine: string; count: number }, text: ShareText, fonts = ""): string {
  return page(
    fonts,
    `<div><p class="kicker">${sprayImg()}${esc(text.home_kicker)}</p><h1>${esc(d.heroLine)}</h1><p class="line">${esc(fill(text.home_line, { count: d.count.toLocaleString("en-US") }))}</p></div>` +
      `<p class="stamps"><span class="stamp closed">${esc(text.stamp_closed)}</span><span class="stamp">${esc(text.stamp_again)}</span></p><p class="foot">${esc(text.footer)}</p>`,
  );
}

/** Open Graph tags for the app shell (`index.html`), so every route without its own stub page shows the generic site image. */
export function siteOgTags(imageUrl: string, title: string, description: string): string {
  return `<meta property="og:title" content="${esc(title)}"><meta property="og:description" content="${esc(description)}">` +
    `<meta property="og:image" content="${esc(imageUrl)}"><meta property="og:image:width" content="${SHARE_W}"><meta property="og:image:height" content="${SHARE_H}">` +
    `<meta name="twitter:card" content="summary_large_image">`;
}

/** A stub page for a social crawler: Open Graph tags that name the share image, then a redirect to the app view (no script). */
export function stubHtml(opts: { title: string; description: string; imageUrl: string; target: string }): string {
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>${esc(opts.title)}</title>` +
    `<meta property="og:title" content="${esc(opts.title)}"><meta property="og:description" content="${esc(opts.description)}">` +
    `<meta property="og:image" content="${esc(opts.imageUrl)}"><meta property="og:image:width" content="${SHARE_W}"><meta property="og:image:height" content="${SHARE_H}">` +
    `<meta name="twitter:card" content="summary_large_image"><meta http-equiv="refresh" content="0; url=${esc(opts.target)}"></head>` +
    `<body><p><a href="${esc(opts.target)}">${esc(opts.title)}</a></p></body></html>`;
}

/** Group headline zombies by neighborhood (stable order: most first, then name). */
export function neighborhoodSummaries<T extends { neighborhood: string | null; type_family: string; tier: string }>(zs: readonly T[], label: (family: string) => string): NeighborhoodShare[] {
  const by = new Map<string, Map<string, number>>();
  for (const z of zs) {
    if (z.tier !== "headline" || !z.neighborhood) continue;
    const m = by.get(z.neighborhood) ?? new Map<string, number>();
    m.set(z.type_family, (m.get(z.type_family) ?? 0) + 1);
    by.set(z.neighborhood, m);
  }
  return [...by.entries()]
    .map(([neighborhood, fam]) => {
      const sorted = [...fam.entries()].sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1));
      return { neighborhood, count: sorted.reduce((n, [, c]) => n + c, 0), topFamilyLabel: sorted[0] ? label(sorted[0][0]) : null, topFamilyCount: sorted[0]?.[1] ?? 0 };
    })
    .sort((a, b) => b.count - a.count || (a.neighborhood < b.neighborhood ? -1 : 1));
}

export interface ShareZombie { zombie_id: string; tier: string; type_family: string; neighborhood: string | null; gap_days: number }

export interface ShareTargets<Z extends ShareZombie> {
  /** The judge-mode tour's zombies, in tour order. A tour id that no shard holds is listed in `missingTour`. */
  tour: Z[];
  missingTour: string[];
  neighborhoods: NeighborhoodShare[];
}

/**
 * Which pages get their own share image (REQ-WEB-LINKS.2, the nightly deploy): the judge-mode tour's zombies and the neighborhoods.
 * Districts and the home page are drawn from their own files by the build script. Every other page, including every other
 * possible zombie, shows the generic site image, so the build draws a few dozen images instead of one per zombie.
 */
export function selectShareTargets<Z extends ShareZombie>(zombies: readonly Z[], tourIds: readonly string[], label: (family: string) => string): ShareTargets<Z> {
  const byId = new Map(zombies.map((z) => [z.zombie_id, z]));
  const tour: Z[] = [];
  const missingTour: string[] = [];
  for (const id of tourIds) {
    const z = byId.get(id);
    if (z) tour.push(z);
    else missingTour.push(id);
  }
  return { tour, missingTour, neighborhoods: neighborhoodSummaries(zombies.filter((z) => z.tier === "headline"), label) };
}

/** One progress line for the build log: `make-share-images: 12/60 images (20%), 8.4 s`. */
export function progressLine(done: number, total: number, elapsedMs: number): string {
  const pct = total === 0 ? 100 : Math.floor((done / total) * 100);
  return `make-share-images: ${done}/${total} images (${pct}%), ${(elapsedMs / 1000).toFixed(1)} s`;
}
