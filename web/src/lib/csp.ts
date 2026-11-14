/**
 * Content Security Policy for the static host (REQ-WEB-PERF.3, REQ-OPS-HOST.3). Same-origin only: no directive names an
 * outside host, `*` or `unsafe-eval`. MapLibre and deck.gl need blob: workers and data: or blob: images; React and the map set
 * inline styles, hence style-src 'unsafe-inline' (scripts never are). Plain TypeScript with no enums so Node can run it
 * directly (scripts/write-headers.ts) and Vite, vitest and the tests can import the same single source.
 */
export const CSP_DIRECTIVES: Record<string, string[]> = {
  "default-src": ["'self'"],
  "script-src": ["'self'"],
  "style-src": ["'self'", "'unsafe-inline'"],
  "img-src": ["'self'", "data:", "blob:"],
  "font-src": ["'self'"],
  "connect-src": ["'self'"],
  "worker-src": ["'self'", "blob:"],
  "child-src": ["'self'", "blob:"],
  "object-src": ["'none'"],
  "base-uri": ["'self'"],
  "form-action": ["'self'"],
  "frame-ancestors": ["'none'"],
};

export function cspString(d: Record<string, string[]> = CSP_DIRECTIVES): string {
  return Object.entries(d)
    .map(([k, v]) => `${k} ${v.join(" ")}`)
    .join("; ");
}

/** Headers sent with every response. */
export function securityHeaders(): Record<string, string> {
  return {
    "Content-Security-Policy": cspString(),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
  };
}

/** The Netlify `_headers` file: one block for every path. */
export function headersFile(): string {
  const lines = Object.entries(securityHeaders()).map(([k, v]) => `  ${k}: ${v}`);
  return `/*\n${lines.join("\n")}\n`;
}
