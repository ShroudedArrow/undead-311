---
inclusion: always
---
# Tech stack and decisions

## Pipeline (Python)
- Python 3.11 (the sandbox default), managed with `uv`. Lint/format with `ruff`. Tests with `pytest` + `hypothesis` (property-based tests are required, see `testing.md`).
- Data engine: **DuckDB** (SQL-first) with Parquet files under `$DATA_DIR/processed/`. Prefer SQL in DuckDB over pandas loops.
- Spatial: haversine distance in SQL plus a coarse grid bucket for candidate pairs (avoid O(n^2) joins). Optional: DuckDB `spatial` extension.
- Statistics: `statsmodels` / `scipy`; survival curves with `lifelines` (Kaplan-Meier).
- Outputs for the web app are **static files** written to `web/public/data/`: JSON for aggregates and per-zombie cards, compact columnar files for map points.
- Data access: download Analyze Boston CSV resources (find URLs via the CKAN MCP server or CKAN `package_show`). Never commit raw data; commit only `data/sample/` (small) for tests.

## Web app (TypeScript)
- Vite + React + TypeScript. Map: MapLibre GL JS; use deck.gl layers for large point sets and the time-lapse.
- Basemap: a free, no-API-key source (e.g., OpenFreeMap styles or self-hosted Protomaps PMTiles), restyled by hand to the palette in `design-system.md`. Always show OpenStreetMap attribution. Do not ship a default dark theme.
- Visual design and copy: follow `design-system.md` and `voice.md`. User-facing copy that humans must write is left as `TODO-COPY:` placeholders.
- Tests: `vitest` + `fast-check` for property tests of client-side logic; Playwright for end-to-end checks.
- Accessibility: keyboard navigation, `prefers-reduced-motion`, a table view that mirrors the map.

## Data contracts and performance
- Every exported file has a JSON Schema in `/schemas/`; the pipeline validates on export and stamps `data_version`. Outputs are deterministic (stable IDs, sorted).
- Payload budget: under ~3 MB for the first view. Shard by neighborhood/year; lazy-load evidence cards; precompress.
- Nightly job writes `status.json` (last run, row counts, anomalies); the site shows it; failures alert the team. If a run fails, the site keeps the last good data.
- Security: no third-party scripts at runtime, a Content Security Policy, `npm audit` / `pip-audit` in CI.
- No runtime third-party requests at all: self-host the fonts (OFL licensed) and a Boston-area basemap extract (PMTiles) on the same static host, so the site can't break if an outside service changes before Jan 29.
- The pipeline writes the DuckDB file atomically (build to a temp file, then rename), because the DuckDB MCP server opens short-lived read-only connections and must never catch a half-written file.
- Map markers: render from a small sprite atlas of 3–5 scanned spray-circle variants (deck.gl IconLayer), not individual SVGs.

## Hosting and automation
- Static hosting (Netlify via the Kiro Netlify power, or GitHub Pages). The site must keep working with no server.
- Nightly data refresh via a scheduled GitHub Actions workflow that runs the pipeline and redeploys. The Kiro Crew App (separate repo) handles agentic work: weekly "Resurrection Report" to Discord and labeling new closure texts.
- No secrets in the repo. No paid runtime APIs.

## Data location, snapshots, and freezes
- Raw and processed data live outside git tracking: $DATA_DIR outside the repo on local or Azure runs; the gitignored .local-data/ folder in Kiro Web (default `~/undead311-data/` on a local machine). Code reads paths from `DATA_DIR`.
- **Self-correcting fallback (required):** whenever `DATA_DIR` is unset, missing, or not writable, code must fall back to `<repo root>/.local-data/data`, and the uv cache (`UV_CACHE_DIR`) to `<repo root>/.local-data/uv-cache`. Resolve `<repo root>` with `pwd -P` (or `git rev-parse --show-toplevel`) at run time, never a hard-coded mount path, so a different mount path in a future session cannot break anything. Create the folder there if needed. Only `data/sample/` and `data/labels/` are in the repo.
- **Kiro Web:** the sandbox home is read-only and `/tmp` does not persist between commands, so `DATA_DIR` points into the gitignored in-repo folder `.local-data/` (`DATA_DIR=/projects/sandbox/undead-311/.local-data/data`, `UV_CACHE_DIR=/projects/sandbox/undead-311/.local-data/uv-cache`). Agents never read raw files directly; they query through DuckDB. Nothing in `.local-data/` is ever committed.
- A dated **judging snapshot** (data through a fixed date) drives the video, README numbers, and validation. The site always shows "Data as of <date>".
- Pin versions: `.python-version`, `uv.lock`, `.nvmrc`, `package-lock.json`. Pin GitHub Actions to tagged versions.
- After the Dec 4 deadline the judged repo's code does not change. The nightly refresh runs from a separate `undead-311-data` repo that publishes data files the static site loads.
- Footer on every page: "Independent project. Not affiliated with the City of Boston." Credit OpenStreetMap; list data licenses.

## Models and effort
Use the strongest model with high reasoning effort for requirements, design, and reviews; a faster model for routine implementation tasks.
