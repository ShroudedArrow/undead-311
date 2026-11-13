# Design: haunted-web

## Overview
A static Vite + React + TypeScript app in `web/`. MapLibre GL JS renders a self-hosted Boston PMTiles extract that is restyled by hand to the palette. deck.gl draws the zombie markers (IconLayer, 3–5 scanned spray-circle sprites; placeholder sprites until the owner's scans exist). State lives in the URL (filters, selection, tier toggle), so permalinks come for free. No server, no runtime third-party requests.

## Architecture
```
web/public/data/** (pipeline exports, or fixtures from data/sample)
   │  fetch (same origin) ─► lib/parse/* (schema-derived validators) ─► lib/store (URL state + loaded data)
   │                                                           │
   ▼                                                           ▼
routes: / (Map + Table toggle) · /zombie/:id (Card) · /scorecard · /methods · /judge · /street · /repeat · /corrections
components: MapView, MarkerLayer, Filters, ZombieTable, AutopsyCard (Triplicate), Scorecard, SurvivalChart, FunnelChart,
            Leaderboard, TierToggle, JudgeTour, DataAsOf, Footer, ReportErrorLink, Sliders, StreetSearch, TimeLapse
copy: web/src/copy/en.json (+ es.json) via a typed t(key) helper; no string literals in components
```

### Key modules
| Module | Role | Requirements |
|---|---|---|
| `lib/parse/` | Types and validators generated from `/schemas/*.json` (`json-schema-to-typescript` plus a small runtime validator, `ajv` in standalone build mode so the CSP needs no `eval`) | REQ-WEB-DATA |
| `lib/filter.ts` | Pure `applyFilters(zombies, filters, tierMode) -> Zombie[]` and `aggregate(zombies, by) -> Counts` | REQ-WEB-MAP.2–3, REQ-WEB-TABLE, REQ-WEB-TIER |
| `lib/url.ts` | `encodeState`, `decodeState` (round-trip) | REQ-WEB-LINKS |
| `lib/tour.ts` | Tour builder: confirmed or provisional selection rule; the build-time check | REQ-WEB-JUDGE |
| `components/AutopsyCard/` | Triplicate form, responsive bottom sheet, lazy shard load | REQ-WEB-CARD |
| `styles/tokens.css` | The six palette tokens, type scale, focus ring; nothing else defines color | REQ-WEB-DESIGN |
| `scripts/` (web) | Build-time: CSP header file, budget check, corrections page, share images (Playwright screenshots of a share template), address index | REQ-WEB-PERF, -FRESH, -LINKS, -STREET |

### Tier display
Headline zombies are solid pink spray circles. With the toggle on, `source_unknown` and `sensitivity` zombies are pink outlines with an Asphalt stroke. Their cards carry a tier note from `en.json`. Counts always show "headline N" first.

### Judge-mode selection
`judge_tour.json` lists three zombie IDs and `provisional: bool`.
- The production build (`VITE_MODE=production`) runs `scripts/check-tour.ts`. It fails unless `provisional` is false and every ID is in `validation.json.confirmed`.
- Preview and dev builds accept `provisional: true` and render a notice.

This resolves the conflict between "judge mode is demo-critical (Nov 17)" and "only confirmed validation zombies" (field validation happens Nov 21–22).

## Data models
The TypeScript types are generated from the engine and stats schemas: `Zombie`, `Card`, `Points` (columnar arrays), `Scorecard`, `Curve`, `Group`, `Grid`, `Status`, `Validation`, `JudgeTour`. `Filters = {neighborhoods: string[], departments: string[], families: string[], years: number[]}` (empty = all). `TierMode = "headline" | "all"`.

## Correctness properties (fast-check)
| # | Property | testing.md | Requirements |
|---|---|---|---|
| W1 | Contract: the parsers accept every file that validates against its schema (generated from the schema), and reject files with a missing required field | 16 (web half) | REQ-WEB-DATA.1 |
| W2 | `applyFilters` returns a subset of its input; with empty filters and `all` tier it returns the input | — | REQ-WEB-MAP.2 |
| W3 | Filters commute and are idempotent: applying A then B equals B then A equals A∧B | — | REQ-WEB-MAP.3 |
| W4 | Map set = table set = counted set for any filters and tier mode | — | REQ-WEB-MAP.3, REQ-WEB-TABLE |
| W5 | `aggregate` counts sum to the filtered total, and no count is negative | 3 (client side) | REQ-WEB-MAP.2 |
| W6 | Headline mode never contains a `source_unknown` or `sensitivity` zombie, and the headline count is unchanged when the toggle is on | owner (new) | REQ-WEB-TIER |
| W7 | URL state round-trips: `decodeState(encodeState(s)) = s` | — | REQ-WEB-LINKS |
| W8 | Tour check: a production tour is accepted only if every ID is confirmed | — | REQ-WEB-JUDGE.2 |

Unit tests cover components with vitest and Testing Library. The Playwright e2e test (`make e2e`) covers the judge-mode path on a phone and a desktop viewport: open the site, start judge mode, see three cards, skip, reach the map. It also checks keyboard-only operation and reduced motion.

## Error handling
A panel whose data fails to parse shows the `en.json` error state for that panel (TODO-COPY voice sample). Other panels keep working. A missing optional file (survival before credibility) hides its panel and shows nothing broken. If the latest status is a failure, the "Data as of" date of the last good data stays visible.

## Testing strategy and dependencies
vitest + fast-check (properties W1–W8), Testing Library, Playwright (e2e, axe via `@axe-core/playwright`, screenshots for reviewer-ux).

New dependencies: `react`, `react-dom`, `react-router-dom`, `maplibre-gl`, `pmtiles`, `deck.gl` (`@deck.gl/core`, `@deck.gl/layers`, `@deck.gl/mapbox`), `ajv`, `json-schema-to-typescript` (dev), `vitest`, `fast-check`, `@testing-library/react`, `@playwright/test`, `@axe-core/playwright`, and `@fontsource/public-sans` plus `@fontsource/courier-prime` (self-hosted OFL fonts). Each is noted in the PR description. Charts are plain SVG components, with no chart library.
