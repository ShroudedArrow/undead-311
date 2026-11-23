/**
 * Long lists show a first page and grow by one page at a time ("Show 25 more"). The number of rows shown lives in the URL as `n`,
 * so a shared link or a reload shows the same rows. REQ-WEB-LINKS.1.
 */
export const PAGE_SIZE = 25;
const MAX_SHOWN = 5000;

/** Rows shown according to the `n` parameter: a whole number of pages, at least one, never more than the cap. */
export function decodeShown(params: URLSearchParams | string): number {
  const p = typeof params === "string" ? new URLSearchParams(params) : params;
  const n = Math.floor(Number(p.get("n")));
  if (!Number.isFinite(n) || n < PAGE_SIZE) return PAGE_SIZE;
  return Math.min(MAX_SHOWN, Math.ceil(n / PAGE_SIZE) * PAGE_SIZE);
}

/** Write `n` into the parameters; the first page leaves no trace in the URL. */
export function writeShown(p: URLSearchParams, shown: number): URLSearchParams {
  if (shown <= PAGE_SIZE) p.delete("n");
  else p.set("n", String(shown));
  return p;
}
