/**
 * Card shard naming (REQ-WEB-CARD.4, REQ-EXP-SIZE): cards are sharded by neighborhood and year, file `cards/<slug>-<year>.json`.
 * The same slug rule is used by scripts/make-fixtures.mjs. Proposal to the engine: confirm this naming (ops proposal).
 */
export function slug(s: string | null | undefined): string {
  return (s || "unknown").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

export function shardKey(neighborhood: string | null | undefined, year: number): string {
  return `${slug(neighborhood)}-${year}`;
}

export function shardFile(neighborhood: string | null | undefined, year: number): string {
  return `cards/${shardKey(neighborhood, year)}.json`;
}
