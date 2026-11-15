/**
 * Share images and permalinks (REQ-WEB-LINKS.1-2). Plain TypeScript with no Vite imports, so the build script
 * (scripts/make-share-images.ts) and the browser use the same file names and the same template.
 * Share images are static files rendered at build time from a template; there is no runtime service.
 */

import { spraySvg } from "../map/sprites.ts";

export const SHARE_W = 1200;
export const SHARE_H = 630;

const PALETTE = { concrete: "#CDCBC6", asphalt: "#2E3134", white: "#F4F4EF", pink: "#FF3EA5" } as const;

/** A file-name-safe slug: lower case letters and digits, single dashes. "101001:101002" gives "101001-101002". */
export function shareSlug(s: string | null | undefined): string {
  return (s || "unknown").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "unknown";
}

/** Path of a zombie's share image under the site root (no leading slash). */
export const zombieImagePath = (zombieId: string): string => `share/zombie/${shareSlug(zombieId)}.png`;
/** Path of a neighborhood's share image under the site root. */
export const neighborhoodImagePath = (name: string | null | undefined): string => `share/neighborhood/${shareSlug(name)}.png`;

export const esc = (s: string): string => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
export const fill = (template: string, params: Record<string, string | number>): string => template.replace(/\{(\w+)\}/g, (m, k: string) => (k in params ? String(params[k]) : m));

export interface ShareText {
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
body{background:${PALETTE.concrete};color:${PALETTE.asphalt};font-family:"Public Sans",system-ui,sans-serif;display:flex;flex-direction:column;justify-content:space-between;padding:56px 64px}
.kicker{font-size:32px;font-weight:700;margin:0}
.circle{display:inline-block;width:64px;height:64px;vertical-align:-14px;margin-right:14px}
h1{font-size:76px;line-height:1.05;margin:20px 0 0;max-width:1000px}
.line{font-size:36px;line-height:1.3;margin:24px 0 0;max-width:1000px}
.stamps{display:flex;gap:24px;margin:0}
.stamp{font-family:"Courier Prime",monospace;font-weight:700;font-size:34px;border:5px solid ${PALETTE.asphalt};padding:6px 18px;background:${PALETTE.white}}
.stamp.closed{text-decoration:line-through}
.foot{font-size:24px;margin:0}`;

const page = (fonts: string, body: string): string => `<!doctype html><html lang="en"><head><meta charset="utf-8"><style>${css(fonts)}</style></head><body>${body}</body></html>`;

/** The 1200 by 630 page for one possible zombie. `fonts` is the @font-face CSS (file URLs when rendered at build time). */
export function zombieShareHtml(d: ZombieShare, text: ShareText, fonts = ""): string {
  const where = fill(text.zombie_where, { family: d.familyLabel, neighborhood: d.neighborhood });
  return page(
    fonts,
    `<div><p class="kicker">${sprayImg()}${esc(text.zombie_kicker)}</p><h1>${esc(where)}</h1><p class="line">${esc(fill(text.zombie_line, { gap: d.gap }))}</p></div>` +
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
